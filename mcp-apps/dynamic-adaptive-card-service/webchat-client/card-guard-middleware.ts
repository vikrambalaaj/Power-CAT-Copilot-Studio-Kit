/**
 * Web Chat Client-Side Adaptive Card Guard & Telemetry Middleware
 * 
 * Features:
 * 1. Single-Click Submit Guard: Immediately disables DOM inputs on first click to eliminate stale/double clicks.
 * 2. Client-Side Error Boundary: Catches AdaptiveCard.render() exceptions and displays a fallback HTML card.
 * 3. Telemetry Integration: Dispatches custom window telemetry events for monitoring.
 */

export interface WebChatCardAttachment {
  contentType: string;
  content: Record<string, any>;
}

export function createCardGuardMiddleware(telemetryCallback?: (eventName: string, data: any) => void) {
  return () => (next: any) => (card: { attachment: WebChatCardAttachment }) => {
    if (card.attachment.contentType !== "application/vnd.microsoft.card.adaptive") {
      return next(card);
    }

    const rawContent = card.attachment.content;

    // Return custom renderer component function
    return (renderProps: any) => {
      const containerDiv = document.createElement("div");
      containerDiv.className = "copilot-adaptive-card-container";

      try {
        // Assume AdaptiveCards SDK is loaded in global or imported scope
        const AdaptiveCardsSDK = (window as any).AdaptiveCards;
        if (!AdaptiveCardsSDK) {
          throw new Error("AdaptiveCards SDK not found on window object.");
        }

        const adaptiveCard = new AdaptiveCardsSDK.AdaptiveCard();
        adaptiveCard.hostConfig = new AdaptiveCardsSDK.HostConfig({
          fontFamily: "'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif",
          spacing: { small: 8, medium: 16, large: 24, extraLarge: 32 },
          separator: { lineThickness: 1, lineColor: "#E0E0E0" },
        });

        adaptiveCard.parse(rawContent);

        let isSubmitted = false;

        // Wire Action Handler with Stale Click Disabler
        adaptiveCard.onExecuteAction = async (action: any) => {
          if (isSubmitted) {
            console.warn("[CardGuard] Ignored duplicate click on submitted card.");
            return;
          }
          isSubmitted = true;

          // 1. Disable all DOM interactive controls inside container immediately
          disableContainerInteractivity(containerDiv);

          // 2. Telemetry tracking
          if (telemetryCallback) {
            telemetryCallback("CardSubmitted", {
              actionId: action?.data?.actionSubmitId,
              verb: action?.data?.actionVerb,
              timestamp: Date.now(),
            });
          }

          // 3. Dispatch to WebChat store
          if (renderProps?.onExecuteAction) {
            renderProps.onExecuteAction(action);
          }
        };

        const renderedElement = adaptiveCard.render();
        if (!renderedElement) {
          throw new Error("AdaptiveCard.render() produced empty element.");
        }

        containerDiv.appendChild(renderedElement);
        return containerDiv;
      } catch (err: any) {
        console.error("[CardGuard] Adaptive Card render error. Activating HTML Fallback:", err);

        if (telemetryCallback) {
          telemetryCallback("CardRenderError", {
            error: err.message,
            cardTitle: rawContent?.body?.[0]?.text,
          });
        }

        // Render clean, accessible HTML Fallback view
        return renderHtmlFallback(rawContent, err.message);
      }
    };
  };
}

function disableContainerInteractivity(container: HTMLElement): void {
  const interactiveElements = container.querySelectorAll("button, input, select, textarea");
  interactiveElements.forEach((el) => {
    (el as HTMLInputElement).disabled = true;
    el.setAttribute("aria-disabled", "true");
  });
  container.classList.add("card-state-submitted");
}

function renderHtmlFallback(content: any, errorMessage: string): HTMLElement {
  const fallbackDiv = document.createElement("div");
  fallbackDiv.className = "copilot-card-fallback-alert";
  fallbackDiv.style.cssText = `
    padding: 16px;
    border-radius: 8px;
    background-color: #FFF9F5;
    border: 1px solid #FED7AA;
    color: #431407;
    font-family: 'Segoe UI', sans-serif;
    margin: 8px 0;
  `;

  const title = content?.body?.[0]?.text || "Card Preview";
  const summary = content?.body?.[1]?.text || "Content is available in text mode.";

  fallbackDiv.innerHTML = `
    <div style="font-weight: 600; font-size: 14px; margin-bottom: 4px;">
      ⚠️ Display Fallback: ${escapeHtml(title)}
    </div>
    <div style="font-size: 13px; color: #7C2D12;">
      ${escapeHtml(summary)}
    </div>
    <div style="margin-top: 8px; font-size: 11px; color: #9A3412;">
      (Note: Rich interactive controls could not be initialized.)
    </div>
  `;

  return fallbackDiv;
}

function escapeHtml(str: string): string {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
