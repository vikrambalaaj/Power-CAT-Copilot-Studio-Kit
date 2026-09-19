import crypto from "crypto";
import fs from "fs";
import path from "path";

export interface TicketPayload {
  sessionId: string;
  actionIdPrefix: string;
  templateId: string;
  issuedAt: number;
  expiresAt: number;
}

export class IdempotencySigner {
  private secretKey: string;
  private static sharedProcessedTokens: Set<string> = new Set<string>();

  public static getStoragePath(): string {
    if (process.env.IDEMPOTENCY_STORAGE_PATH) {
      return process.env.IDEMPOTENCY_STORAGE_PATH;
    }
    if (process.env.AZURE_STORAGE_MOUNT_PATH) {
      return path.join(process.env.AZURE_STORAGE_MOUNT_PATH, "card_consumed_tokens.json");
    }
    if (process.env.VELORA_STATE_DIR) {
      return path.join(process.env.VELORA_STATE_DIR, "card_consumed_tokens.json");
    }
    return "/tmp/card_consumed_tokens.json";
  }

  public static getStorageDirectory(): string {
    if (process.env.IDEMPOTENCY_STORAGE_DIR) {
      return process.env.IDEMPOTENCY_STORAGE_DIR;
    }
    if (process.env.AZURE_STORAGE_MOUNT_PATH) {
      return path.join(process.env.AZURE_STORAGE_MOUNT_PATH, "card_idempotency");
    }
    if (process.env.VELORA_STATE_DIR) {
      return path.join(process.env.VELORA_STATE_DIR, "card_idempotency");
    }
    const legacyPath = IdempotencySigner.getStoragePath();
    return path.join(path.dirname(legacyPath), "card_idempotency");
  }

  static {
    IdempotencySigner.loadPersistedTokens();
  }

  constructor(secretKey?: string) {
    const configuredSecret = secretKey || process.env.TOKEN_SIGNING_SECRET;
    if (!configuredSecret) {
      if (process.env.NODE_ENV === "production" && process.env.REQUIRE_EXPLICIT_SIGNING_SECRET === "true") {
        throw new Error("FATAL: TOKEN_SIGNING_SECRET must be explicitly configured in production environments.");
      }
      this.secretKey = "enterprise_dev_secret_key_84920";
    } else {
      this.secretKey = configuredSecret;
    }
  }

  private static loadPersistedTokens(): void {
    try {
      // 1. Warm up from atomic tokens directory
      const storageDir = IdempotencySigner.getStorageDirectory();
      if (fs.existsSync(storageDir)) {
        const files = fs.readdirSync(storageDir);
        for (const file of files) {
          if (file.endsWith(".json")) {
            const base = file.replace(".json", "");
            IdempotencySigner.sharedProcessedTokens.add(base);
          }
        }
      }

      // 2. Warm up from legacy JSON file if present
      const storagePath = IdempotencySigner.getStoragePath();
      if (fs.existsSync(storagePath)) {
        const raw = fs.readFileSync(storagePath, "utf8");
        const list = JSON.parse(raw);
        if (Array.isArray(list)) {
          for (const item of list) {
            if (typeof item === "string") {
              IdempotencySigner.sharedProcessedTokens.add(item);
            }
          }
        }
      }
    } catch {
      // Best effort warm up
    }
  }

  /**
   * Generates a signed, tamper-proof ticket token containing session and timing metadata.
   */
  public generateTicket(sessionId: string, templateId: string, ttlSeconds: number = 3600): { ticketToken: string; actionIdPrefix: string } {
    const actionIdPrefix = `act_${Date.now()}_${crypto.randomBytes(4).toString("hex")}`;
    const issuedAt = Math.floor(Date.now() / 1000);
    const expiresAt = issuedAt + ttlSeconds;

    const payload: TicketPayload = {
      sessionId,
      actionIdPrefix,
      templateId,
      issuedAt,
      expiresAt,
    };

    const payloadB64 = Buffer.from(JSON.stringify(payload)).toString("base64url");
    const signature = crypto
      .createHmac("sha256", this.secretKey)
      .update(payloadB64)
      .digest("base64url");

    return {
      ticketToken: `${payloadB64}.${signature}`,
      actionIdPrefix,
    };
  }

  /**
   * Verifies ticket authenticity, expiration, and ensures one-time execution (idempotency).
   * Backed by durable shared multi-replica atomic storage.
   */
  public verifyAndConsumeTicket(ticketToken: string): { valid: boolean; error?: string; payload?: TicketPayload } {
    if (!ticketToken || typeof ticketToken !== "string") {
      return { valid: false, error: "Malformed or missing ticket token." };
    }

    const segments = ticketToken.split(".");
    if (segments.length !== 2 || !segments[0] || !segments[1]) {
      return { valid: false, error: "Noncanonical token structure: token must contain exactly two segments." };
    }

    const [payloadB64, signature] = segments;
    const expectedSig = crypto
      .createHmac("sha256", this.secretKey)
      .update(payloadB64)
      .digest("base64url");

    const sigBuf = Buffer.from(signature);
    const expBuf = Buffer.from(expectedSig);
    if (sigBuf.length !== expBuf.length || !crypto.timingSafeEqual(sigBuf, expBuf)) {
      return { valid: false, error: "Invalid signature: token has been tampered with." };
    }

    let payload: TicketPayload;
    try {
      payload = JSON.parse(Buffer.from(payloadB64, "base64url").toString("utf8"));
    } catch {
      return { valid: false, error: "Failed to decode token payload." };
    }

    const canonicalToken = `${payloadB64}.${signature}`;
    const stableId = payload.actionIdPrefix;
    const tokenHash = crypto.createHash("sha256").update(canonicalToken).digest("hex");
    const actionHash = stableId ? crypto.createHash("sha256").update(stableId).digest("hex") : "";

    // 1. Fast in-memory check
    if (
      IdempotencySigner.sharedProcessedTokens.has(canonicalToken) ||
      IdempotencySigner.sharedProcessedTokens.has(tokenHash) ||
      (stableId && (IdempotencySigner.sharedProcessedTokens.has(stableId) || IdempotencySigner.sharedProcessedTokens.has(actionHash)))
    ) {
      return { valid: false, error: "Token already consumed: stale or duplicate click." };
    }

    const now = Math.floor(Date.now() / 1000);
    if (now > payload.expiresAt) {
      return { valid: false, error: "Token has expired." };
    }

    // 2. Durable atomic shared directory verification
    const storageDir = IdempotencySigner.getStorageDirectory();
    try {
      if (!fs.existsSync(storageDir)) {
        fs.mkdirSync(storageDir, { recursive: true });
      }
    } catch (dirErr: any) {
      return {
        valid: false,
        error: `Storage failure: unable to create storage directory: ${dirErr?.message || dirErr}`,
      };
    }

    const tokenFilePath = path.join(storageDir, `${tokenHash}.json`);
    const actionFilePath = actionHash ? path.join(storageDir, `act_${actionHash}.json`) : null;

    if (fs.existsSync(tokenFilePath) || (actionFilePath && fs.existsSync(actionFilePath))) {
      IdempotencySigner.sharedProcessedTokens.add(canonicalToken);
      IdempotencySigner.sharedProcessedTokens.add(tokenHash);
      if (stableId) {
        IdempotencySigner.sharedProcessedTokens.add(stableId);
        IdempotencySigner.sharedProcessedTokens.add(actionHash);
      }
      return { valid: false, error: "Token already consumed: stale or duplicate click." };
    }

    // Atomic claim on token hash
    let tokenFd: number;
    try {
      tokenFd = fs.openSync(tokenFilePath, "wx");
    } catch (err: any) {
      if (err.code === "EEXIST") {
        IdempotencySigner.sharedProcessedTokens.add(canonicalToken);
        IdempotencySigner.sharedProcessedTokens.add(tokenHash);
        return { valid: false, error: "Token already consumed: stale or duplicate click." };
      }
      return {
        valid: false,
        error: `Storage failure: failed to atomically record token consumption: ${err.message}`,
      };
    }

    // If stable action ID present, atomically claim action ID
    let actionFd: number | null = null;
    if (actionFilePath) {
      try {
        actionFd = fs.openSync(actionFilePath, "wx");
      } catch (err: any) {
        fs.closeSync(tokenFd);
        try { fs.unlinkSync(tokenFilePath); } catch {}
        if (err.code === "EEXIST") {
          IdempotencySigner.sharedProcessedTokens.add(stableId);
          IdempotencySigner.sharedProcessedTokens.add(actionHash);
          return { valid: false, error: "Token already consumed: stale or duplicate click." };
        }
        return {
          valid: false,
          error: `Storage failure: failed to atomically record action consumption: ${err.message}`,
        };
      }
    }

    try {
      const record = JSON.stringify({
        canonicalToken,
        tokenHash,
        actionIdPrefix: stableId,
        sessionId: payload.sessionId,
        templateId: payload.templateId,
        issuedAt: payload.issuedAt,
        expiresAt: payload.expiresAt,
        consumedAt: Date.now(),
      });
      fs.writeFileSync(tokenFd, record, "utf8");
      if (actionFd !== null) {
        fs.writeFileSync(actionFd, record, "utf8");
      }
    } catch (writeErr: any) {
      return {
        valid: false,
        error: `Storage failure: failed to write consumption record: ${writeErr?.message || writeErr}`,
      };
    } finally {
      try { fs.closeSync(tokenFd); } catch {}
      if (actionFd !== null) {
        try { fs.closeSync(actionFd); } catch {}
      }
    }

    // Update memory sets
    IdempotencySigner.sharedProcessedTokens.add(canonicalToken);
    IdempotencySigner.sharedProcessedTokens.add(tokenHash);
    if (stableId) {
      IdempotencySigner.sharedProcessedTokens.add(stableId);
      IdempotencySigner.sharedProcessedTokens.add(actionHash);
    }

    // 3. Update legacy store file as backward compatibility
    try {
      const storagePath = IdempotencySigner.getStoragePath();
      const legacyDir = path.dirname(storagePath);
      if (!fs.existsSync(legacyDir)) {
        fs.mkdirSync(legacyDir, { recursive: true });
      }
      const existing: string[] = [];
      if (fs.existsSync(storagePath)) {
        const parsed = JSON.parse(fs.readFileSync(storagePath, "utf8"));
        if (Array.isArray(parsed)) existing.push(...parsed);
      }
      existing.push(canonicalToken);
      if (stableId) existing.push(stableId);
      const trimmed = existing.slice(-10000);
      const tempLegacy = `${storagePath}.${process.pid}.${Date.now()}.tmp`;
      fs.writeFileSync(tempLegacy, JSON.stringify(trimmed), "utf8");
      fs.renameSync(tempLegacy, storagePath);
    } catch {
      // Legacy mirror best-effort; atomic dir is authoritative
    }

    return { valid: true, payload };
  }
}

