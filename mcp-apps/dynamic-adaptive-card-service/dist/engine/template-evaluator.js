import { TemplateRegistry } from "./template-registry.js";
import { ValidatorSanitizer } from "./validator-sanitizer.js";
import { FallbackGenerator } from "./fallback-generator.js";
import { IdempotencySigner } from "../security/idempotency-signer.js";
export class TemplateEvaluator {
    registry;
    validator;
    fallbackGen;
    signer;
    constructor(registry, validator, fallbackGen, signer) {
        this.registry = registry || new TemplateRegistry();
        this.validator = validator || new ValidatorSanitizer();
        this.fallbackGen = fallbackGen || new FallbackGenerator();
        this.signer = signer || new IdempotencySigner();
    }
    renderCard(request) {
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
        try {
            // 2. Generate signed one-time ticket token for idempotency
            const { ticketToken, actionIdPrefix } = this.signer.generateTicket(sessionId, templateId, request.ttlSeconds || 3600);
            // 3. Prepare data payload
            const hydrationContext = {
                ...request.data,
                ticketToken,
                actionIdPrefix,
            };
            // 4. Hydrate template using Adaptive Cards Templating engine
            const expanded = template.expand({ $root: hydrationContext });
            const rawEvaluatedCard = typeof expanded === "string" ? JSON.parse(expanded) : expanded;
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
        }
        catch (err) {
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
    inferTemplate(data) {
        if (data.primaryMetric)
            return "metrics-card";
        if (data.inputLabel || data.instructions)
            return "input-form-card";
        if (data.facts && !data.actions)
            return "fact-grid-card";
        return "approval-card";
    }
    getSigner() {
        return this.signer;
    }
}
