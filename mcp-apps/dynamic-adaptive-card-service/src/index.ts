import Fastify from "fastify";
import { TemplateEvaluator } from "./engine/template-evaluator.js";

const fastify = Fastify({
  logger: process.env.NODE_ENV !== "test",
});

const evaluator = new TemplateEvaluator();

// 0. Root Status Endpoint
fastify.get("/", async (request, reply) => {
  reply.header("Content-Type", "text/html; charset=utf-8");
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Velora Dynamic Adaptive Card Service</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; }
    .card { background: #1e293b; border-radius: 12px; padding: 2rem; max-width: 650px; margin: 0 auto; border: 1px solid #334155; }
    h1 { color: #38bdf8; margin-top: 0; }
    a { color: #38bdf8; }
    .badge { background: #10b981; color: #042f2e; padding: 3px 8px; border-radius: 9999px; font-weight: bold; font-size: 0.8rem; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Velora Adaptive Card Service <span class="badge">ACTIVE</span></h1>
    <p>Enterprise Dynamic Adaptive Card Rendering &amp; Validation Service for Copilot Studio and Velora One.</p>
    <ul>
      <li><a href="/health">/health</a> - Service health check &amp; uptime</li>
      <li><a href="/templates">/templates</a> - List registered templates</li>
      <li><code>POST /render-card</code> - Render card with template data</li>
      <li><code>POST /validate-submission</code> - Verify and consume idempotency ticket</li>
    </ul>
  </div>
</body>
</html>`;
});

// 1. Healthcheck Endpoint
fastify.get("/health", async () => {
  return {
    status: "ok",
    service: "dynamic-adaptive-card-service",
    version: "1.0.0",
    uptimeSeconds: Math.floor(process.uptime()),
  };
});

// 2. List Available Templates
fastify.get("/templates", async () => {
  return {
    templates: evaluator.getRegistry().listTemplates(),
    targetSchemaVersion: "1.5",
  };
});

// 3. Render Adaptive Card Dynamically Endpoint
fastify.post<{
  Body: {
    templateId?: string;
    sessionId?: string;
    data: Record<string, any>;
    ttlSeconds?: number;
  };
}>("/render-card", async (request, reply) => {
  const { templateId, sessionId, data, ttlSeconds } = request.body || {};

  if (!data || typeof data !== "object") {
    return reply.status(400).send({
      error: "Bad Request",
      message: "Field 'data' object is required.",
    });
  }

  if (ttlSeconds !== undefined) {
    if (
      typeof ttlSeconds !== "number" ||
      !Number.isFinite(ttlSeconds) ||
      !Number.isInteger(ttlSeconds) ||
      ttlSeconds <= 0 ||
      ttlSeconds > 86400
    ) {
      return reply.status(400).send({
        error: "Bad Request",
        message: "Field 'ttlSeconds' must be a finite positive integer <= 86400.",
      });
    }
  }

  const result = evaluator.renderCard({
    templateId,
    sessionId,
    data,
    ttlSeconds,
  });

  return reply.status(result.success ? 200 : 422).send(result);
});

// 4. Validate Submission & Idempotency Endpoint
fastify.post<{
  Body: {
    ticketToken: string;
    submittedData?: Record<string, any>;
  };
}>("/validate-submission", async (request, reply) => {
  const { ticketToken, submittedData } = request.body || {};

  if (!ticketToken) {
    return reply.status(400).send({
      valid: false,
      error: "Missing required 'ticketToken'.",
    });
  }

  const signer = evaluator.getSigner();
  const outcome = signer.verifyAndConsumeTicket(ticketToken, submittedData);

  if (!outcome.valid) {
    return reply.status(403).send({
      valid: false,
      error: outcome.error,
    });
  }

  return reply.status(200).send({
    valid: true,
    message: "Submission validated successfully and token consumed.",
    payload: outcome.payload,
    submittedData,
  });
});

const start = async () => {
  const port = Number(process.env.PORT) || 8086;
  const host = process.env.HOST || "0.0.0.0";
  try {
    await fastify.listen({ port, host });
    console.log(`Adaptive Card Service running at http://${host}:${port}`);
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};

if (process.env.NODE_ENV !== "test") {
  start();
}

export { fastify, evaluator };
