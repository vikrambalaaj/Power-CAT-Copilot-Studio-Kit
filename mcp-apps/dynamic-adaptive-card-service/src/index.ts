import Fastify from "fastify";
import { TemplateEvaluator } from "./engine/template-evaluator.js";

const fastify = Fastify({
  logger: process.env.NODE_ENV !== "test",
});

const evaluator = new TemplateEvaluator();

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
    templates: ["approval-card", "fact-grid-card", "input-form-card", "metrics-card"],
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
  const outcome = signer.verifyAndConsumeTicket(ticketToken);

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
  const port = Number(process.env.PORT) || 8080;
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
