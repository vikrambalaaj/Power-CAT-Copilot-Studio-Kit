#!/usr/bin/env bash
# Build only. This script never changes a running Container App.
set -euo pipefail

MODE="${1:-local}"
TAG="${2:?Usage: build_image.sh local|acr <unique-tag>}"
IMAGE_NAME="${IMAGE_NAME:-velora-mcp-sf}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REVISION="$(git -C "$APP_DIR" rev-parse HEAD)"
if [[ -n "$(git -C "$APP_DIR" status --porcelain -- .)" ]]; then
    REVISION="${REVISION}-working-tree"
fi

case "$MODE" in
  local)
    docker build --platform linux/amd64 \
      --build-arg "SOURCE_REVISION=$REVISION" \
      --tag "$IMAGE_NAME:$TAG" "$APP_DIR"
    ;;
  acr)
    : "${ACR_NAME:?Set ACR_NAME to the target Azure Container Registry}"
    # An explicit staging allowlist keeps tenant settings, reports, logs and
    # credentials out of the remote build upload as well as the final image.
    STAGING_DIR="$(mktemp -d)"
    trap 'rm -rf "$STAGING_DIR"' EXIT
    mkdir -p "$STAGING_DIR/deploy"
    cp "$APP_DIR/Dockerfile" "$APP_DIR/.dockerignore" \
      "$APP_DIR/pyproject.toml" "$APP_DIR/requirements.txt" "$STAGING_DIR/"
    cp "$APP_DIR/deploy/copilot-workforce-card-openapi.json" "$STAGING_DIR/deploy/"
    cp -R "$APP_DIR/successfactors_mcp" "$APP_DIR/shared_mcp" "$STAGING_DIR/"
    python3 - "$STAGING_DIR" <<'PY'
from pathlib import Path
import shutil
import sys
root = Path(sys.argv[1])
for item in list(root.rglob('*')):
    if item.name in ('__pycache__', 'logs') and item.is_dir():
        shutil.rmtree(item)
    elif item.is_file() and (item.suffix == '.pyc' or item.name.startswith('.env')):
        item.unlink()
PY
    az acr build --registry "$ACR_NAME" --platform linux/amd64 \
      --image "$IMAGE_NAME:$TAG" --build-arg "SOURCE_REVISION=$REVISION" \
      "$STAGING_DIR"
    ;;
  *) echo 'Mode must be local or acr.' >&2; exit 2 ;;
esac
