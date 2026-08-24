export class ValidatorSanitizer {
    allowedDomains;
    maxPayloadSizeBytes;
    constructor(allowedDomains = ["microsoft.com", "powerapps.com", "azure.com", "github.com", "office.com"], maxPayloadSizeBytes = 15360) {
        this.allowedDomains = allowedDomains;
        this.maxPayloadSizeBytes = maxPayloadSizeBytes;
    }
    /**
     * Sanitizes and validates the compiled Adaptive Card JSON against enterprise bounds.
     */
    sanitizeAndValidate(card) {
        const rawJson = JSON.stringify(card);
        const payloadSizeBytes = Buffer.byteLength(rawJson, "utf8");
        const errors = [];
        // 1. Check size budget
        if (payloadSizeBytes > this.maxPayloadSizeBytes) {
            errors.push(`Payload size (${payloadSizeBytes} bytes) exceeds limit (${this.maxPayloadSizeBytes} bytes).`);
        }
        // 2. Validate Schema and Version
        if (card.type !== "AdaptiveCard") {
            errors.push("Invalid root element: must be 'AdaptiveCard'.");
        }
        if (!card.version || (card.version !== "1.5" && card.version !== "1.6" && card.version !== "1.4")) {
            errors.push(`Unsupported or missing Adaptive Card version: ${card.version}. Target 1.5.`);
        }
        // 3. Deep sanitization of URLs and text
        const sanitized = JSON.parse(rawJson);
        this.walkAndSanitize(sanitized, errors);
        return {
            valid: errors.length === 0,
            sanitizedCard: errors.length === 0 ? sanitized : undefined,
            errors,
            payloadSizeBytes,
        };
    }
    walkAndSanitize(node, errors) {
        if (!node || typeof node !== "object")
            return;
        if (Array.isArray(node)) {
            for (const item of node) {
                this.walkAndSanitize(item, errors);
            }
            return;
        }
        // Sanitize TextBlock text (strip script tags or dangerous html)
        if (typeof node.text === "string") {
            node.text = node.text.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, "");
        }
        // Check OpenUrl actions against domain whitelist
        if (node.type === "Action.OpenUrl" && typeof node.url === "string") {
            try {
                const parsedUrl = new URL(node.url);
                const isAllowed = this.allowedDomains.some((d) => parsedUrl.hostname === d || parsedUrl.hostname.endsWith(`.${d}`));
                if (!isAllowed) {
                    errors.push(`Disallowed domain in Action.OpenUrl: ${parsedUrl.hostname}`);
                }
            }
            catch {
                errors.push(`Invalid URL format in Action.OpenUrl: ${node.url}`);
            }
        }
        // Walk child properties
        for (const key of Object.keys(node)) {
            if (typeof node[key] === "object") {
                this.walkAndSanitize(node[key], errors);
            }
        }
    }
}
