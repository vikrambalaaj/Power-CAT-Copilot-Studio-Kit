import { TemplateRegistry } from "./template-registry.js";
import { ValidatorSanitizer, ValidationResult } from "./validator-sanitizer.js";
import { FallbackGenerator, FallbackRepresentation } from "./fallback-generator.js";
import { IdempotencySigner } from "../security/idempotency-signer.js";

export interface RenderCardRequest {
  templateId?: string;
  sessionId?: string;
  data: Record<string, any>;
  ttlSeconds?: number;
}

export interface RenderCardResponse {
  success: boolean;
  templateUsed: string;
  latencyMs: number;
  ticketToken?: string;
  adaptiveCard?: Record<string, any>;
  fallback: FallbackRepresentation;
  validation: ValidationResult;
}

export class TemplateEvaluator {
  private registry: TemplateRegistry;
  private validator: ValidatorSanitizer;
  private fallbackGen: FallbackGenerator;
  private signer: IdempotencySigner;

  constructor(
    registry?: TemplateRegistry,
    validator?: ValidatorSanitizer,
    fallbackGen?: FallbackGenerator,
    signer?: IdempotencySigner
  ) {
    this.registry = registry || new TemplateRegistry();
    this.validator = validator || new ValidatorSanitizer();
    this.fallbackGen = fallbackGen || new FallbackGenerator();
    this.signer = signer || new IdempotencySigner();
  }

  public renderCard(request: RenderCardRequest): RenderCardResponse {
    const startTime = performance.now();
    const fallback = this.fallbackGen.generateFallback(request.data);
    const templateId = request.templateId || this.inferTemplate(request.data);
    const sessionId = request.sessionId || `sess_${Date.now()}`;

    // 1. Check template existence
    const template = this.registry.getTemplate(templateId);
    if (!template) {
      const latencyMs = Math.round(performance.now() - startTime);
      return {
        success: false,
        templateUsed: templateId,
        latencyMs,
        fallback,
        validation: {
          valid: false,
          errors: [`Template '${templateId}' not found. Available: ${this.registry.listTemplates().join(", ")}`],
          payloadSizeBytes: 0,
        },
      };
    }

    if (request.ttlSeconds !== undefined) {
      if (
        typeof request.ttlSeconds !== "number" ||
        !Number.isFinite(request.ttlSeconds) ||
        !Number.isInteger(request.ttlSeconds) ||
        request.ttlSeconds <= 0 ||
        request.ttlSeconds > 86400
      ) {
        const latencyMs = Math.round(performance.now() - startTime);
        return {
          success: false,
          templateUsed: templateId,
          latencyMs,
          fallback,
          validation: {
            valid: false,
            errors: ["Invalid ttlSeconds: must be a finite positive integer <= 86400."],
            payloadSizeBytes: 0,
          },
        };
      }
    }

    try {
      // 2. Generate signed one-time ticket token for idempotency
      const { ticketToken, actionIdPrefix } = this.signer.generateTicket(
        sessionId,
        templateId,
        request.ttlSeconds || 3600,
        request.data
      );

      // 3. Prepare data payload
      const hydrationContext = {
        ...request.data,
        ticketToken,
        actionIdPrefix,
      };

      // 4. Hydrate template using Adaptive Cards Templating engine
      const expanded = template.expand({ $root: hydrationContext });
      const rawEvaluatedCard = typeof expanded === "string" ? JSON.parse(expanded) : expanded;

      // Include the immutable preview separately from editable card inputs. Teams
      // submits action data plus input fields, not the original render request.
      const bindActions = (node: any): void => {
        if (!node || typeof node !== "object") return;
        if (node.type === "Action.Submit") {
          node.data = { ...(node.data || {}), ticketToken, sessionId, approvedData: request.data };
          return;
        }
        for (const value of Object.values(node)) {
          if (Array.isArray(value)) value.forEach(bindActions);
          else bindActions(value);
        }
      };
      bindActions(rawEvaluatedCard);

      // 5. Sanitize & Validate (Schema v1.5, URL whitelist, 15KB size check)
      const validation = this.validator.sanitizeAndValidate(rawEvaluatedCard);

      const latencyMs = Math.round(performance.now() - startTime);

      if (!validation.valid) {
        return {
          success: false,
          templateUsed: templateId,
          latencyMs,
          ticketToken,
          fallback,
          validation,
        };
      }

      return {
        success: true,
        templateUsed: templateId,
        latencyMs,
        ticketToken,
        adaptiveCard: validation.sanitizedCard,
        fallback,
        validation,
      };
    } catch (err: any) {
      const latencyMs = Math.round(performance.now() - startTime);
      return {
        success: false,
        templateUsed: templateId,
        latencyMs,
        fallback,
        validation: {
          valid: false,
          errors: [`Template evaluation exception: ${err.message}`],
          payloadSizeBytes: 0,
        },
      };
    }
  }

  /**
   * Infers template type from AI payload shape if not explicitly provided.
   */
  private inferTemplate(data: Record<string, any>): string {
    if (data.primaryMetric) return "metrics-card";
    if (data.inputLabel || data.instructions) return "input-form-card";
    if (data.facts && !data.actions) return "fact-grid-card";
    return "approval-card";
  }

  public getSigner(): IdempotencySigner {
    return this.signer;
  }

  public getRegistry(): TemplateRegistry {
    return this.registry;
  }
}
