#!/bin/bash
set -e

# Script to build all 4 MCP images for Azure Container Apps deployment
# Registry prefix can be passed as argument 1, e.g.: ./build_all_images.sh myregistry.azurecr.io

REGISTRY="${1:-}"
TAG="${2:-latest}"

if [ -n "$REGISTRY" ]; then
    REGISTRY_PREFIX="${REGISTRY}/"
else
    REGISTRY_PREFIX=""
fi

echo "========================================="
echo "Building 4 MCP Images for Azure Container Apps"
echo "Tag suffix: ${TAG}"
echo "Registry: ${REGISTRY:-local (no registry prefix)}"
echo "========================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. SuccessFactors MCP
echo ""
echo "[1/4] Building SF (SuccessFactors) image..."
docker build -t "${REGISTRY_PREFIX}velora-mcp-sf:${TAG}" -f "${SCRIPT_DIR}/ask-successfactors/Dockerfile" "${SCRIPT_DIR}/ask-successfactors"

# 2. SAP S/4HANA MCP
echo ""
echo "[2/4] Building SAP S/4HANA image..."
docker build -t "${REGISTRY_PREFIX}velora-mcp-s4hana:${TAG}" -f "${SCRIPT_DIR}/ask-s4hana/Dockerfile" "${SCRIPT_DIR}/ask-s4hana"

# 3. SAP Analytics Cloud (SAC) MCP
echo ""
echo "[3/4] Building SAC (SAP Analytics Cloud) image..."
docker build -t "${REGISTRY_PREFIX}velora-mcp-sac:${TAG}" -f "${SCRIPT_DIR}/ask-sac/Dockerfile" "${SCRIPT_DIR}/ask-sac"

# 4. Facilitator MCP
echo ""
echo "[4/5] Building Facilitator image..."
docker build -t "${REGISTRY_PREFIX}velora-mcp-facilitator:${TAG}" -f "${SCRIPT_DIR}/ask-facilitator/Dockerfile" "${SCRIPT_DIR}/ask-facilitator"

# 5. Dynamic Adaptive Card Service
echo ""
echo "[5/5] Building Dynamic Adaptive Card Service image..."
docker build -t "${REGISTRY_PREFIX}velora-mcp-card-service:${TAG}" -f "${SCRIPT_DIR}/dynamic-adaptive-card-service/Dockerfile" "${SCRIPT_DIR}/dynamic-adaptive-card-service"

echo ""
echo "========================================="
echo "All 5 images built successfully!"
echo " - ${REGISTRY_PREFIX}velora-mcp-sf:${TAG} (Port 8082)"
echo " - ${REGISTRY_PREFIX}velora-mcp-s4hana:${TAG} (Port 8083)"
echo " - ${REGISTRY_PREFIX}velora-mcp-sac:${TAG} (Port 8084)"
echo " - ${REGISTRY_PREFIX}velora-mcp-facilitator:${TAG} (Port 8080)"
echo " - ${REGISTRY_PREFIX}velora-mcp-card-service:${TAG} (Port 8085)"
echo "========================================="

if [ -n "$REGISTRY" ]; then
    echo ""
    echo "To push all images to Azure Container Registry, run:"
    echo "  docker push ${REGISTRY_PREFIX}velora-mcp-sf:${TAG}"
    echo "  docker push ${REGISTRY_PREFIX}velora-mcp-s4hana:${TAG}"
    echo "  docker push ${REGISTRY_PREFIX}velora-mcp-sac:${TAG}"
    echo "  docker push ${REGISTRY_PREFIX}velora-mcp-facilitator:${TAG}"
    echo "  docker push ${REGISTRY_PREFIX}velora-mcp-card-service:${TAG}"
fi
