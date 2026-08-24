"""Validate and build the Microsoft 365/Teams app package."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile


APP_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = APP_ROOT / "agent" / "appPackage"
OUTPUT = APP_ROOT / "velora-hcm-agent.zip"
CARD_FILES = tuple(
    str(path.relative_to(PACKAGE_ROOT))
    for path in sorted((PACKAGE_ROOT / "adaptive-cards").glob("*.json"))
)
FILES = (
    "manifest.json",
    "declarativeAgent.json",
    "ai-plugin.json",
    "mcp-tools.json",
    "s4hana-plugin.json",
    "s4hana-mcp-tools.json",
    "sac-plugin.json",
    "sac-mcp-tools.json",
    "facilitator-plugin.json",
    "instruction.txt",
    "color.png",
    "outline.png",
) + CARD_FILES
PLACEHOLDERS = (
    "REPLACE_WITH_PLUGIN_VAULT_REFERENCE_ID",
    "REPLACE_WITH_S4_PLUGIN_VAULT_REFERENCE_ID",
    "REPLACE_WITH_SAC_PLUGIN_VAULT_REFERENCE_ID",
)


def load_json(name: str) -> dict:
    with (PACKAGE_ROOT / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def validate() -> None:
    missing = [name for name in FILES if not (PACKAGE_ROOT / name).is_file()]
    if missing:
        raise SystemExit(f"Missing package files: {', '.join(missing)}")

    combined = "\n".join((PACKAGE_ROOT / name).read_text(errors="ignore") for name in FILES)
    unresolved = [value for value in PLACEHOLDERS if value in combined]
    if unresolved:
        raise SystemExit(
            "Package still contains deployment placeholders: " + ", ".join(unresolved)
        )

    manifest = load_json("manifest.json")
    for plugin_name, tools_name in (
        ("ai-plugin.json", "mcp-tools.json"),
        ("s4hana-plugin.json", "s4hana-mcp-tools.json"),
        ("sac-plugin.json", "sac-mcp-tools.json"),
    ):
        plugin = load_json(plugin_name)
        tools = load_json(tools_name).get("tools", [])
        declared = {item["name"] for item in plugin.get("functions", [])}
        described = {item["name"] for item in tools}
        runtime = plugin["runtimes"][0]

        if declared != described or declared != set(runtime.get("run_for_functions", [])):
            raise SystemExit(f"{plugin_name} functions and tool descriptions do not match")
        if urlparse(runtime["spec"]["url"]).scheme != "https":
            raise SystemExit(f"The {plugin_name} production runtime URL must use HTTPS")

    for plugin_name in ("ai-plugin.json", "s4hana-plugin.json", "sac-plugin.json", "facilitator-plugin.json"):
        for function in load_json(plugin_name).get("functions", []):
            semantics = function.get("capabilities", {}).get("response_semantics", {})
            template = semantics.get("static_template", {}).get("file", "")
            if semantics.get("properties", {}).get("template_selector") != "$.adaptiveCard":
                raise SystemExit(f"{plugin_name}:{function.get('name')} must prefer $.adaptiveCard")
            if not template.startswith("./adaptive-cards/") or not (PACKAGE_ROOT / template.removeprefix("./")).is_file():
                raise SystemExit(f"{plugin_name}:{function.get('name')} has an invalid card fallback template")

    agent_actions = {item["file"] for item in load_json("declarativeAgent.json").get("actions", [])}
    required_plugins = {"ai-plugin.json", "s4hana-plugin.json", "sac-plugin.json", "facilitator-plugin.json"}
    if not required_plugins.issubset(agent_actions):
        raise SystemExit("The declarative agent must reference every packaged MCP plugin")
    if not manifest.get("copilotAgents", {}).get("declarativeAgents"):
        raise SystemExit("The Microsoft 365 manifest does not reference a declarative agent")
    if len(CARD_FILES) < 10:
        raise SystemExit("The Copilot package must contain the complete Adaptive Card catalog")
    for name in CARD_FILES:
        card = load_json(name)
        if card.get("type") != "AdaptiveCard" or card.get("version") != "1.5":
            raise SystemExit(f"{name} must be an Adaptive Card v1.5 template")


def main() -> None:
    validate()
    with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(PACKAGE_ROOT / name, arcname=name)
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    main()
