import fs from "fs";
import path from "path";
import * as ACData from "adaptivecards-templating";

import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export class TemplateRegistry {
  private templates: Map<string, ACData.Template> = new Map();
  private rawJsonMap: Map<string, Record<string, any>> = new Map();

  constructor() {
    this.loadBuiltinTemplates();
  }

  private loadBuiltinTemplates(): void {
    const candidateDirs = [
      path.resolve(__dirname, "../templates"),
      path.resolve(__dirname, "./templates"),
      path.resolve(process.cwd(), "src/templates"),
      path.resolve(process.cwd(), "dist/templates"),
      path.resolve(process.cwd(), "templates"),
    ];

    for (const dir of candidateDirs) {
      if (fs.existsSync(dir)) {
        const files = fs.readdirSync(dir).filter((f) => f.endsWith(".json"));
        for (const file of files) {
          const templateId = path.basename(file, ".json");
          if (!this.templates.has(templateId)) {
            const rawContent = fs.readFileSync(path.join(dir, file), "utf8");
            const parsed = JSON.parse(rawContent);
            this.registerTemplate(templateId, parsed);
          }
        }
      }
    }
  }

  public registerTemplate(id: string, rawJson: Record<string, any>): void {
    this.rawJsonMap.set(id, rawJson);
    this.templates.set(id, new ACData.Template(rawJson));
  }

  public getTemplate(id: string): ACData.Template | undefined {
    return this.templates.get(id);
  }

  public listTemplates(): string[] {
    return Array.from(this.templates.keys());
  }

  public hasTemplate(id: string): boolean {
    return this.templates.has(id);
  }
}
