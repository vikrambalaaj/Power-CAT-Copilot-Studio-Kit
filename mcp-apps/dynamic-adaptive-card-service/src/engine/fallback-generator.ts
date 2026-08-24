export interface FallbackRepresentation {
  markdownText: string;
  plainText: string;
  suggestedActions: Array<{ title: string; value: string }>;
}

export class FallbackGenerator {
  /**
   * Generates formatted Markdown and Quick Reply options from raw AI input.
   */
  public generateFallback(data: Record<string, any>): FallbackRepresentation {
    const title = data.cardTitle || data.title || "Information Summary";
    const summary = data.summary || data.instructions || "";
    const facts: Array<{ title: string; value: string }> = data.facts || [];

    // Build Markdown
    const markdownLines: string[] = [`### 📋 ${title}`];

    if (data.badge && data.badge.text) {
      markdownLines.push(`**Status:** \`${data.badge.text}\``);
    }

    if (summary) {
      markdownLines.push(`\n${summary}\n`);
    }

    if (facts.length > 0) {
      markdownLines.push("---");
      for (const fact of facts) {
        markdownLines.push(`* **${fact.title}:** ${fact.value}`);
      }
    }

    if (data.primaryMetric) {
      markdownLines.push(`\n📊 **${data.primaryMetric.label}:** ${data.primaryMetric.value}`);
    }

    // Build Actions / Quick Replies
    const suggestedActions: Array<{ title: string; value: string }> = [];

    if (data.actions && Array.isArray(data.actions)) {
      for (const act of data.actions) {
        suggestedActions.push({
          title: act.title || "Select",
          value: act.title || "Select",
        });
      }
    } else {
      // Default common actions
      suggestedActions.push({ title: "Approve", value: "Approve" });
      suggestedActions.push({ title: "Reject", value: "Reject" });
    }

    // Plain text for SMS / low-bandwidth
    const plainText = `${title}\n${summary}\n` + facts.map((f) => `${f.title}: ${f.value}`).join("\n");

    return {
      markdownText: markdownLines.join("\n"),
      plainText,
      suggestedActions,
    };
  }
}
