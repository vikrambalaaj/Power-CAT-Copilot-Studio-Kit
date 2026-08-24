import fs from "fs";
import path from "path";
import * as ACData from "adaptivecards-templating";
import { fileURLToPath } from "url";
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
export class TemplateRegistry {
    templates = new Map();
    rawJsonMap = new Map();
    constructor() {
        this.loadBuiltinTemplates();
    }
    loadBuiltinTemplates() {
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
    registerTemplate(id, rawJson) {
        this.rawJsonMap.set(id, rawJson);
        this.templates.set(id, new ACData.Template(rawJson));
    }
    getTemplate(id) {
        return this.templates.get(id);
    }
    listTemplates() {
        return Array.from(this.templates.keys());
    }
    hasTemplate(id) {
        return this.templates.has(id);
    }
}
