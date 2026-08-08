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
    "instruction.txt",
    "color.png",
    "outline.png",
) + CARD_FILES
PLACEHOLDERS = (
    "REPLACE_WITH_PLUGIN_VAULT_REFERENCE_ID",
    "REPLACE_WITH_S4_PLUGIN_VAULT_REFERENCE_ID",
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
    ):
        plugin = load_json(plugin_name)
        tools = load_json(tools_name).get("tools", [])
        declared = {item["name"] for item in plugin.get("functions", [])}
        described = {item["name"] for item in tools}
        runtime = plugin["runtimes"][0]
        inline_tools = runtime.get("spec", {}).get("mcp_tool_description", {}).get("tools", [])
        inline_names = {item["name"] for item in inline_tools}

        if declared != described or declared != inline_names or declared != set(runtime.get("run_for_functions", [])):
            raise SystemExit(f"{plugin_name} functions, runtime bindings, and tool descriptions do not match")
        if any(not {"name", "description", "inputSchema"}.issubset(tool) for tool in tools):
            raise SystemExit(f"Every {tools_name} entry must contain name, description, and inputSchema")
        if urlparse(runtime["spec"]["url"]).scheme != "https":
            raise SystemExit(f"The {plugin_name} production runtime URL must use HTTPS")

    agent_actions = {item["file"] for item in load_json("declarativeAgent.json").get("actions", [])}
    if agent_actions != {"ai-plugin.json", "s4hana-plugin.json"}:
        raise SystemExit("The declarative agent must reference both SAP MCP plugins")
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
