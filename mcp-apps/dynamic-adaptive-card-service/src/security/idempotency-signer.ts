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

  static {
    IdempotencySigner.loadPersistedTokens();
  }

  constructor(secretKey?: string) {
    if (!secretKey && !process.env.TOKEN_SIGNING_SECRET && process.env.NODE_ENV === "production") {
      throw new Error("FATAL: TOKEN_SIGNING_SECRET must be explicitly configured in production environments.");
    }
    this.secretKey = secretKey || process.env.TOKEN_SIGNING_SECRET || "enterprise_dev_secret_key_84920";
  }

  private static loadPersistedTokens(): void {
    try {
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

    if (IdempotencySigner.sharedProcessedTokens.has(canonicalToken) || (stableId && IdempotencySigner.sharedProcessedTokens.has(stableId))) {
      return { valid: false, error: "Token already consumed: stale or duplicate click." };
    }

    const now = Math.floor(Date.now() / 1000);
    if (now > payload.expiresAt) {
      return { valid: false, error: "Token has expired." };
    }

    const storagePath = IdempotencySigner.getStoragePath();
    const storageDir = path.dirname(storagePath);
    try {
      if (!fs.existsSync(storageDir)) {
        fs.mkdirSync(storageDir, { recursive: true });
      }
    } catch (dirErr: any) {
      // Fail closed when storage directory is unwritable
      return {
        valid: false,
        error: `Storage failure: unable to create storage directory: ${dirErr?.message || dirErr}`,
      };
    }

    const lockPath = storagePath + ".lock";
    let lockFd: number | null = null;
    const maxWaitMs = 3000;
    const lockStart = Date.now();
    while (lockFd === null) {
      try {
        lockFd = fs.openSync(lockPath, "wx");
      } catch (err: any) {
        if (err.code === "EEXIST") {
          try {
            const stat = fs.statSync(lockPath);
            if (Date.now() - stat.mtimeMs > 5000) {
              fs.unlinkSync(lockPath);
              continue;
            }
          } catch {}
          if (Date.now() - lockStart > maxWaitMs) {
            return {
              valid: false,
              error: "Storage lock timeout: unable to acquire idempotency store lock.",
            };
          }
          const target = Date.now() + 15;
          while (Date.now() < target) {}
        } else {
          return {
            valid: false,
            error: `Storage lock error: ${err.message}`,
          };
        }
      }
    }

    try {
      // Read current persisted tokens under lock
      const diskTokens = new Set<string>();
      if (fs.existsSync(storagePath)) {
        const raw = fs.readFileSync(storagePath, "utf8");
        const list = JSON.parse(raw);
        if (Array.isArray(list)) {
          for (const item of list) {
            if (typeof item === "string") {
              diskTokens.add(item);
              IdempotencySigner.sharedProcessedTokens.add(item);
            }
          }
        }
      }

      if (
        diskTokens.has(canonicalToken) ||
        (stableId && diskTokens.has(stableId)) ||
        IdempotencySigner.sharedProcessedTokens.has(canonicalToken) ||
        (stableId && IdempotencySigner.sharedProcessedTokens.has(stableId))
      ) {
        return { valid: false, error: "Token already consumed: stale or duplicate click." };
      }

      diskTokens.add(canonicalToken);
      IdempotencySigner.sharedProcessedTokens.add(canonicalToken);
      if (stableId) {
        diskTokens.add(stableId);
        IdempotencySigner.sharedProcessedTokens.add(stableId);
      }

      const arr = Array.from(diskTokens).slice(-100000);
      const tempPath = `${storagePath}.${process.pid}.${Date.now()}.tmp`;
      fs.writeFileSync(tempPath, JSON.stringify(arr), "utf8");
      fs.renameSync(tempPath, storagePath);

      return { valid: true, payload };
    } catch (storageErr: any) {
      // Fail closed when store is unavailable or persistence fails
      return {
        valid: false,
        error: `Storage failure: failed to atomically record token consumption: ${storageErr?.message || storageErr}`,
      };
    } finally {
      if (lockFd !== null) {
        try {
          fs.closeSync(lockFd);
          fs.unlinkSync(lockPath);
        } catch {}
      }
    }
  }
}

