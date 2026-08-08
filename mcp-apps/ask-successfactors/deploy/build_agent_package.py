"""Validate and build the Microsoft 365/Teams app package."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile


APP_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = APP_ROOT / "agent" / "appPackage"
OUTPUT = APP_ROOT / "velora-hcm-agent.zip"
FILES = (
    "manifest.json",
    "declarativeAgent.json",
    "ai-plugin.json",
    "mcp-tools.json",
    "instruction.txt",
    "color.png",
    "outline.png",
)
PLACEHOLDERS = (
    "REPLACE_WITH_PLUGIN_VAULT_REFERENCE_ID",
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
    plugin = load_json("ai-plugin.json")
    tools = load_json("mcp-tools.json").get("tools", [])
    declared = {item["name"] for item in plugin.get("functions", [])}
    described = {item["name"] for item in tools}
    runtime = plugin["runtimes"][0]
    inline_tools = runtime.get("spec", {}).get("mcp_tool_description", {}).get("tools", [])
    inline_names = {item["name"] for item in inline_tools}

    if declared != described or declared != inline_names or declared != set(runtime.get("run_for_functions", [])):
        raise SystemExit("Plugin functions, runtime bindings, and MCP tool descriptions do not match")
    if any(not {"name", "description", "inputSchema"}.issubset(tool) for tool in tools):
        raise SystemExit("Every MCP tool description must contain name, description, and inputSchema")
    if urlparse(runtime["spec"]["url"]).scheme != "https":
        raise SystemExit("The production MCP runtime URL must use HTTPS")
    if not manifest.get("copilotAgents", {}).get("declarativeAgents"):
        raise SystemExit("The Microsoft 365 manifest does not reference a declarative agent")


def main() -> None:
    validate()
    with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(PACKAGE_ROOT / name, arcname=name)
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    main()
