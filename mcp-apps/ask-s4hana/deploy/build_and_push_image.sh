#!/bin/bash
set -e

# ==============================================================================
# Build & Deploy Script for SAP S/4HANA Finance MCP Server
# Target Compatibility: Azure Container Apps, Azure App Service, Docker, GHCR
# ==============================================================================

TAG="${1:-1.0.0}"
IMAGE_NAME="${IMAGE_NAME:-velora-mcp-s4hana}"
GHCR_REPO="${GHCR_REPO:-ghcr.io/vikrambalaaj/${IMAGE_NAME}}"
ACR_NAME="${ACR_NAME:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=========================================================="
echo "Building S/4HANA MCP Image"
echo "Tag:         ${TAG}"
echo "Context:     ${ROOT_DIR}"
echo "=========================================================="

cd "${ROOT_DIR}"

# Build local images with tags
docker build \
  -t "${IMAGE_NAME}:${TAG}" \
  -t "${IMAGE_NAME}:latest" \
  -t "${GHCR_REPO}:${TAG}" \
  -t "${GHCR_REPO}:latest" \
  .

echo "✓ Local Docker image built successfully with tags:"
echo "   - ${IMAGE_NAME}:${TAG}"
echo "   - ${IMAGE_NAME}:latest"
echo "   - ${GHCR_REPO}:${TAG}"
echo "   - ${GHCR_REPO}:latest"

# Optional: Push to Azure Container Registry (ACR)
if [ -n "$ACR_NAME" ]; then
  ACR_LOGIN_SERVER="${ACR_NAME}.azurecr.io"
  echo ""
  echo "--> Pushing to Azure Container Registry: ${ACR_LOGIN_SERVER}..."
  docker tag "${IMAGE_NAME}:${TAG}" "${ACR_LOGIN_SERVER}/${IMAGE_NAME}:${TAG}"
  docker tag "${IMAGE_NAME}:${TAG}" "${ACR_LOGIN_SERVER}/${IMAGE_NAME}:latest"
  docker push "${ACR_LOGIN_SERVER}/${IMAGE_NAME}:${TAG}"
  docker push "${ACR_LOGIN_SERVER}/${IMAGE_NAME}:latest"
  echo "✓ Pushed to ACR: ${ACR_LOGIN_SERVER}/${IMAGE_NAME}:${TAG}"
fi

# Optional: Push to GHCR
if [ "$PUSH_GHCR" = "true" ]; then
  echo ""
  echo "--> Pushing to GitHub Container Registry: ${GHCR_REPO}..."
  docker push "${GHCR_REPO}:${TAG}"
  docker push "${GHCR_REPO}:latest"
  echo "✓ Pushed to GHCR: ${GHCR_REPO}:${TAG}"
fi

echo "=========================================================="
echo "Deployment image ready for Azure Container Apps!"
echo "=========================================================="
