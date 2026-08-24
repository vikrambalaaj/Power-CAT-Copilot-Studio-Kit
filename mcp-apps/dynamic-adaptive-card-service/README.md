# Enterprise Dynamic Adaptive Card Service for Copilot Studio

A high-performance, resilient microservice and client guard library for dynamically rendering and securing **Adaptive Cards (Schema v1.5)** in **Microsoft Copilot Studio Agents** based on AI outputs and user inputs.

## Key Features

1. **Ultra Low Latency (< 15ms)**: Uses pre-compiled in-memory templates evaluated via `adaptivecards-templating`.
2. **Universal Compatibility (Schema v1.5)**: Targeted at Schema v1.5 to guarantee seamless rendering across Microsoft Teams (Desktop & Mobile), Omnichannel Live Chat, and Web Chat without crashes.
3. **Idempotency & Stale Click Guard**: Cryptographically signed one-time `ticketToken` in button payloads to prevent duplicate or stale submissions from historical cards.
4. **Security & Sanitization**: Strict 15KB payload budget (protects Teams 28KB limit), XSS stripping, and `Action.OpenUrl` domain whitelisting.
5. **Multi-Layered Fallbacks**: Automatic generation of formatted Markdown and Quick Reply suggested actions for plain-text channels (SMS, WhatsApp, email) or broken JSON.
6. **Client-Side Web Chat Middleware**: Complete JavaScript middleware providing single-click DOM disabling and error boundary fallback.

---

## Service Endpoints

### 1. `POST /render-card`
Renders an Adaptive Card from structured AI output data.
```json
{
  "templateId": "approval-card",
  "sessionId": "session-123",
  "data": {
    "cardTitle": "Invoice Approval",
    "summary": "Acme Corp invoice for $4,500.00",
    "facts": [{ "title": "Vendor", "value": "Acme Corp" }]
  }
}
```

### 2. `POST /validate-submission`
Validates the one-time `ticketToken` submitted from an `Action.Submit` button.
```json
{
  "ticketToken": "ey..."
}
```

---

## Directory Structure

- `src/engine/`: Template registry, hydration evaluator, fallback generator, and validator.
- `src/security/`: HMAC-SHA256 token signing and idempotency checks.
- `src/templates/`: Reusable, pre-compiled Adaptive Card JSON templates.
- `webchat-client/`: Client-side WebChat middleware for DOM disabling and rendering error catch.
- `copilot-studio/`: Ready-to-use Power Fx formula snippets and OpenAPI 3.0 Custom Connector schema.
- `test/`: Automated Vitest test suite.
