import crypto from "crypto";
import fs from "fs";

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
  private static storagePath: string = process.env.IDEMPOTENCY_STORAGE_PATH || "/tmp/card_consumed_tokens.json";

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
      if (fs.existsSync(IdempotencySigner.storagePath)) {
        const raw = fs.readFileSync(IdempotencySigner.storagePath, "utf8");
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
      // Best effort load
    }
  }

  private static persistTokens(): void {
    try {
      const arr = Array.from(IdempotencySigner.sharedProcessedTokens).slice(-100000);
      fs.writeFileSync(IdempotencySigner.storagePath, JSON.stringify(arr), "utf8");
    } catch {
      // Best effort persist
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

    // Refresh from disk in case another process consumed it
    IdempotencySigner.loadPersistedTokens();
    if (IdempotencySigner.sharedProcessedTokens.has(canonicalToken) || (stableId && IdempotencySigner.sharedProcessedTokens.has(stableId))) {
      return { valid: false, error: "Token already consumed: stale or duplicate click." };
    }

    const now = Math.floor(Date.now() / 1000);
    if (now > payload.expiresAt) {
      return { valid: false, error: "Token has expired." };
    }

    // Mark canonical token and stable action ID as consumed
    IdempotencySigner.sharedProcessedTokens.add(canonicalToken);
    if (stableId) {
      IdempotencySigner.sharedProcessedTokens.add(stableId);
    }
    IdempotencySigner.persistTokens();

    return { valid: true, payload };
  }
}

