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

  it("7. Should enforce durable shared idempotency across separate instances", () => {
    const signer1 = new IdempotencySigner("test-secret-key-12345");
    const signer2 = new IdempotencySigner("test-secret-key-12345");
    const { ticketToken } = signer1.generateTicket("session-shared", "approval-card", 3600);

    // Instance 1 consumes ticket
    const res1 = signer1.verifyAndConsumeTicket(ticketToken);
    expect(res1.valid).toBe(true);

    // Instance 2 (different replica) attempts to consume the same ticket
    const res2 = signer2.verifyAndConsumeTicket(ticketToken);
    expect(res2.valid).toBe(false);
    expect(res2.error).toContain("already consumed");
  });

  it("8. Should register and render all new enterprise templates under 15KB", () => {
    const templates = evaluator.getRegistry().listTemplates();
    expect(templates).toContain("executive-attention-card");
    expect(templates).toContain("executive-briefing-card");
    expect(templates).toContain("recommendation-card");
    expect(templates).toContain("vendor-decision-card");
    expect(templates).toContain("meeting-actions-card");
    expect(templates).toContain("benchmark-card");

    // Test recommendation-card render
    const recResult = evaluator.renderCard({
      templateId: "recommendation-card",
      data: {
        recommendationTitle: "Freeze Credit for Delinquent Accounts",
        reportingPeriod: "Q3 2026",
        categoryBadge: "RISK",
        actualValue: "AED 42.8M Overdue",
        targetValue: "< AED 10M",
        financialImpact: "+8.4 Days DSO Drag",
        prescribedAction: "Suspend credit facility and dispatch dunning notice.",
        reasoningStep1: "S/4HANA CDS detected >180d balances",
        reasoningStep2: "Credit policy rule §4.2 applies",
        reasoningStep3: "AED 720k bad debt provisioning required",
        reasoningStep4: "Condition sales release on 30% upfront wire",
        confidenceScore: "94% High",
        evidenceQuality: "Authoritative S/4HANA Ledger",
        sourceCitation: "SAP S/4HANA BSID CDS View",
        alertId: "alert-rec-001",
      },
    });
    expect(recResult.success).toBe(true);
    expect(recResult.validation.payloadSizeBytes).toBeLessThan(15360);

    // Test vendor-decision-card render with progressive disclosure
    const decisionResult = evaluator.renderCard({
      templateId: "vendor-decision-card",
      data: {
        decisionTitle: "Vendor Evaluation: Engine Overhaul MRO",
        decisionId: "DEC-2026-881",
        evaluatedDate: "2026-09-19",
        decisionOutcome: "RECOMMENDED",
        scoreStrategic: 92,
        scoreFiscal: 88,
        scorePeer: 84,
        scoreHistorical: 90,
        rationaleSummary: "Highest alignment score with contractual guarantees.",
        comparablePrecedent: "2024 fleet retrofit agreement",
        identifiedRisks: "Supply chain turnaround buffer",
        openQuestions: "Can turnaround be capped at 45 days?",
        confidenceRating: "HIGH (Authoritative)",
        auditRef: "AUD-REF-9921",
        merkleRoot: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      },
    });
    expect(decisionResult.success).toBe(true);
    expect(decisionResult.validation.payloadSizeBytes).toBeLessThan(15360);
  });

  it("9. Should reject invalid, non-integer, or non-finite ttlSeconds", () => {
    const signer = new IdempotencySigner("test-secret-key-12345");
    expect(() => signer.generateTicket("s1", "t1", "not-a-number" as any)).toThrow();
    expect(() => signer.generateTicket("s1", "t1", -10)).toThrow();
    expect(() => signer.generateTicket("s1", "t1", 3.14)).toThrow();

    const renderInvalid = evaluator.renderCard({
      templateId: "approval-card",
      data: { cardTitle: "Test" },
      ttlSeconds: -1,
    });
    expect(renderInvalid.success).toBe(false);
    expect(renderInvalid.validation.errors.some((e) => e.includes("Invalid ttlSeconds"))).toBe(true);
  });

  it("10. Should reject submission when sessionId or approved data has been tampered with", () => {
    const signer = new IdempotencySigner("test-secret-key-12345");
    const approvedData = { amount: 100, vendor: "Acme" };
    const { ticketToken } = signer.generateTicket("session-orig", "approval-card", 3600, approvedData);

    // Mismatched session
    const resWrongSession = signer.verifyAndConsumeTicket(ticketToken, {
      ...approvedData,
      sessionId: "session-attacker",
    });
    expect(resWrongSession.valid).toBe(false);
    expect(resWrongSession.error).toContain("sessionId does not match");

    // Tampered data
    const resTampered = signer.verifyAndConsumeTicket(ticketToken, {
      amount: 999999,
      vendor: "Acme",
      sessionId: "session-orig",
    });
    expect(resTampered.valid).toBe(false);
    expect(resTampered.error).toContain("tampered with");
  });
});


describe("Review: actual submission contract", () => {
  it("rejects omitted approved data without consuming the ticket", () => {
    const signer = new IdempotencySigner("synthetic-secret");
    const { ticketToken } = signer.generateTicket("s", "approval-card", 60, { amount: 10, vendor: "Example" });
    expect(signer.verifyAndConsumeTicket(ticketToken).valid).toBe(false);
    expect(signer.verifyAndConsumeTicket(ticketToken, { vendor: "Example", amount: 10 }).valid).toBe(true);
  });
  it("accepts the data actually submitted by a rendered card with editable comments", () => {
    const evaluator = new TemplateEvaluator();
    const rendered = evaluator.renderCard({ templateId: "approval-card", sessionId: "test-session", data: {
      cardTitle: "Approval", subtitle: "Review", summary: "Approve item", facts: []
    }});
    expect(rendered.success).toBe(true);
    const action = rendered.adaptiveCard!.actions[0];
    expect(evaluator.getSigner().verifyAndConsumeTicket(action.data.ticketToken, { ...action.data, comments: "Reviewed" }).valid).toBe(true);
  });
});
