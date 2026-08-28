"""Build and Package Velora Executive Agent Platform Power Platform Solution and AppPackages."""
from __future__ import annotations

import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOLUTION_DIR = ROOT / "deploy" / "solution"
PRODUCTIVITY_DIR = ROOT / "mcp-apps" / "ask-productivity"


def build_solution_zip():
    """Package solution.xml and customizations.xml into cre2f_VeloraExecutiveAgentPlatform.zip."""
    out_path = ROOT / "deploy" / "cre2f_VeloraExecutiveAgentPlatform.zip"
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(SOLUTION_DIR / "solution.xml", "solution.xml")
        zf.write(SOLUTION_DIR / "customizations.xml", "customizations.xml")
        zf.write(SOLUTION_DIR / "audit_cloud_flows.json", "audit_cloud_flows.json")
    print(f"Created solution archive: {out_path} ({out_path.stat().st_size} bytes)")


def build_productivity_app_package():
    """Package Velora Productivity Agent app package."""
    app_pkg_dir = PRODUCTIVITY_DIR / "agent" / "appPackage"
    out_path = PRODUCTIVITY_DIR / "velora-productivity-agent.zip"
    
    # Create empty color and outline pngs if needed
    for icon in ("color.png", "outline.png"):
        icon_path = app_pkg_dir / icon
        if not icon_path.exists():
            icon_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in app_pkg_dir.iterdir():
            if file.is_file():
                zf.write(file, file.name)
    print(f"Created Productivity Agent app package: {out_path} ({out_path.stat().st_size} bytes)")


def build_hcm_app_package():
    """Package Velora HCM Executive Agent app package."""
    hcm_dir = ROOT / "mcp-apps" / "ask-successfactors"
    app_pkg_dir = hcm_dir / "agent" / "appPackage"
    out_path = hcm_dir / "velora-hcm-agent.zip"
    
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in app_pkg_dir.iterdir():
            if file.is_file():
                zf.write(file, file.name)
    print(f"Created HCM Executive Agent app package: {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    build_solution_zip()
    build_productivity_app_package()
    build_hcm_app_package()
