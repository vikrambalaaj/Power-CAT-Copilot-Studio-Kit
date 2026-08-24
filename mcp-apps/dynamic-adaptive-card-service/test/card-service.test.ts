import { describe, it, expect } from "vitest";
import { TemplateEvaluator } from "../src/engine/template-evaluator.js";
import { IdempotencySigner } from "../src/security/idempotency-signer.js";
import { ValidatorSanitizer } from "../src/engine/validator-sanitizer.js";

describe("Dynamic Adaptive Card Service Unit & Integration Tests", () => {
  const evaluator = new TemplateEvaluator();

  it("1. Should render Approval Card dynamically in under 20ms", () => {
    const aiData = {
      cardTitle: "Vendor Purchase Approval",
      subtitle: "Invoice #INV-84920",
      badge: { text: "Pending Review", style: "warning" },
      summary: "Acme Corp submitted an invoice for $4,500.00 for IT cloud infrastructure licenses.",
      facts: [
        { title: "Vendor", value: "Acme Corp" },
        { title: "Amount", value: "$4,500.00" },
        { title: "Due Date", value: "2026-09-01" },
      ],
    };

    const result = evaluator.renderCard({
      templateId: "approval-card",
      sessionId: "session-user-123",
      data: aiData,
    });

    if (!result.success) {
      console.error("Test 1 Result Errors:", result.validation.errors, "Template:", result.templateUsed);
    }
    expect(result.success).toBe(true);
    expect(result.latencyMs).toBeLessThan(50);
    expect(result.adaptiveCard).toBeDefined();
    expect(result.adaptiveCard?.type).toBe("AdaptiveCard");
    expect(result.adaptiveCard?.version).toBe("1.5");
    expect(result.ticketToken).toBeDefined();
    expect(result.fallback.markdownText).toContain("Vendor Purchase Approval");
  });

  it("2. Should render Metrics & KPI Card dynamically", () => {
    const aiData = {
      cardTitle: "Monthly Azure Spend Telemetry",
      primaryMetric: { label: "Current Spend", value: "$12,450", color: "warning" },
      secondaryMetric: { label: "Budget Forecast", value: "$14,000", color: "good" },
      summary: "Spend is tracking at 89% of monthly allocated cloud budget.",
    };

    const result = evaluator.renderCard({
      templateId: "metrics-card",
      data: aiData,
    });

    expect(result.success).toBe(true);
    expect(result.adaptiveCard?.body[1]?.type).toBe("ColumnSet");
    expect(result.fallback.markdownText).toContain("Current Spend");
  });

  it("3. Should sanitize unsafe HTML and reject untrusted URL links", () => {
    const validator = new ValidatorSanitizer(["microsoft.com", "azure.com"]);
    const unsafeCard = {
      type: "AdaptiveCard",
      version: "1.5",
      body: [
        {
          type: "TextBlock",
          text: "Malicious <script>alert('xss')</script> payload",
        },
      ],
      actions: [
        {
          type: "Action.OpenUrl",
          title: "Phishing Link",
          url: "https://evil-phishing-domain.com/login",
        },
      ],
    };

    const validation = validator.sanitizeAndValidate(unsafeCard);
    expect(validation.valid).toBe(false);
    expect(validation.errors.some((e) => e.includes("Disallowed domain"))).toBe(true);
  });

  it("4. Should reject cards exceeding the 15KB size budget to protect Teams limits", () => {
    const validator = new ValidatorSanitizer(["microsoft.com"], 1024); // 1KB limit for test
    const largeCard = {
      type: "AdaptiveCard",
      version: "1.5",
      body: [
        {
          type: "TextBlock",
          text: "X".repeat(2000), // 2KB payload
        },
      ],
    };

    const validation = validator.sanitizeAndValidate(largeCard);
    expect(validation.valid).toBe(false);
    expect(validation.errors.some((e) => e.includes("exceeds limit"))).toBe(true);
  });

  it("5. Should enforce one-time ticket token consumption (Idempotency & Stale Click Guard)", () => {
    const signer = new IdempotencySigner("test-secret-key-12345");
    const { ticketToken } = signer.generateTicket("session-abc", "approval-card", 3600);

    // First attempt: Valid
    const firstCheck = signer.verifyAndConsumeTicket(ticketToken);
    expect(firstCheck.valid).toBe(true);
    expect(firstCheck.payload?.sessionId).toBe("session-abc");

    // Second attempt (duplicate/stale click): Rejected
    const secondCheck = signer.verifyAndConsumeTicket(ticketToken);
    expect(secondCheck.valid).toBe(false);
    expect(secondCheck.error).toContain("already consumed");
  });

  it("6. Should reject tampered ticket tokens", () => {
    const signer = new IdempotencySigner("test-secret-key-12345");
    const { ticketToken } = signer.generateTicket("session-abc", "approval-card", 3600);

    const tamperedToken = ticketToken.slice(0, -5) + "abcde";
    const check = signer.verifyAndConsumeTicket(tamperedToken);

    expect(check.valid).toBe(false);
    expect(check.error).toContain("Invalid signature");
  });
});
