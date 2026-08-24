import crypto from "crypto";

export interface TicketPayload {
  sessionId: string;
  actionIdPrefix: string;
  templateId: string;
  issuedAt: number;
  expiresAt: number;
}

export class IdempotencySigner {
  private secretKey: string;
  private processedTokens = new Set<string>();

  constructor(secretKey?: string) {
    this.secretKey = secretKey || process.env.TOKEN_SIGNING_SECRET || "enterprise_default_secret_key_84920";
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
    if (!ticketToken || !ticketToken.includes(".")) {
      return { valid: false, error: "Malformed or missing ticket token." };
    }

    const [payloadB64, signature] = ticketToken.split(".");
    const expectedSig = crypto
      .createHmac("sha256", this.secretKey)
      .update(payloadB64)
      .digest("base64url");

    if (signature !== expectedSig) {
      return { valid: false, error: "Invalid signature: token has been tampered with." };
    }

    if (this.processedTokens.has(ticketToken)) {
      return { valid: false, error: "Token already consumed: stale or duplicate click." };
    }

    try {
      const payload: TicketPayload = JSON.parse(Buffer.from(payloadB64, "base64url").toString("utf8"));
      const now = Math.floor(Date.now() / 1000);

      if (now > payload.expiresAt) {
        return { valid: false, error: "Token has expired." };
      }

      // Mark token as consumed for one-time idempotency
      this.processedTokens.add(ticketToken);

      // Simple memory-bound cleanup if set grows large
      if (this.processedTokens.size > 100000) {
        this.processedTokens.clear();
      }

      return { valid: true, payload };
    } catch {
      return { valid: false, error: "Failed to decode token payload." };
    }
  }
}
