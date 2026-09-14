import os
import subprocess
import glob
import shutil

MOCKUP_DIR = "deploy/limad_ui_mockups"
OUT_DIR = "review-evidence/limad-gap-screenshots"
ARTIFACT_DIR = "/Users/vikrambala/.gemini/antigravity-ide/brain/9222f2bd-674d-4bc7-9c57-5a812b6af0c5/screenshots"
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(ARTIFACT_DIR, exist_ok=True)

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

html_files = sorted(glob.glob(f"{MOCKUP_DIR}/*.html"))
print(f"Found {len(html_files)} HTML files to screenshot.")

for h in html_files:
    base = os.path.basename(h).replace(".html", ".png")
    out_png = os.path.join(OUT_DIR, base)
    artifact_png = os.path.join(ARTIFACT_DIR, base)
    abs_html = os.path.abspath(h)
    
    cmd = [
        CHROME_BIN,
        "--headless=new",
        f"--screenshot={out_png}",
        "--window-size=1200,750",
        abs_html
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if os.path.exists(out_png):
        shutil.copy2(out_png, artifact_png)
        size_kb = os.path.getsize(out_png) / 1024
        print(f"✓ Captured: {base} ({size_kb:.1f} KB)")
    else:
        print(f"✗ Failed: {base} -> {res.stderr[:200]}")

print("All screenshots generated successfully!")
