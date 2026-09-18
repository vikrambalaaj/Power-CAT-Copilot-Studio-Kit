#!/bin/bash
set -e

# ==============================================================================
# Script to build and push all 6 MCP & Adaptive Card images for Azure Container Apps
# Usage:
#   ./build_all_images.sh [registry] [tag] [--push]
# Example:
#   ./build_all_images.sh myregistry.azurecr.io v1.0.0 --push
# ==============================================================================

REGISTRY="${1:-}"
TAG="${2:-latest}"
DO_PUSH=false

for arg in "$@"; do
    if [ "$arg" == "--push" ]; then
        DO_PUSH=true
    fi
done

if [ -n "$REGISTRY" ] && [ "$REGISTRY" != "--push" ]; then
    REGISTRY_PREFIX="${REGISTRY}/"
else
    REGISTRY_PREFIX=""
    REGISTRY=""
fi

if [ "$TAG" == "--push" ]; then
    TAG="latest"
fi

echo "========================================="
echo "Building 6 MCP & Card Images for Azure Container Apps"
echo "Tag:      ${TAG}"
echo "Registry: ${REGISTRY:-local (no registry prefix)}"
echo "Push:     ${DO_PUSH}"
echo "========================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIGESTS_FILE="${SCRIPT_DIR}/image-digests.env"

# 1. SuccessFactors MCP (Port 8082)
echo ""
echo "[1/6] Building SF (SuccessFactors) image (Port 8082) for linux/amd64..."
docker build --platform linux/amd64 \
    -t "${REGISTRY_PREFIX}velora-mcp-sf:${TAG}" \
    -t "${REGISTRY_PREFIX}velora-mcp-sf:latest" \
    -f "${SCRIPT_DIR}/ask-successfactors/Dockerfile" "${SCRIPT_DIR}/ask-successfactors"

# 2. SAP S/4HANA MCP (Port 8083)
echo ""
echo "[2/6] Building SAP S/4HANA image (Port 8083) for linux/amd64..."
docker build --platform linux/amd64 \
    -t "${REGISTRY_PREFIX}velora-mcp-s4hana:${TAG}" \
    -t "${REGISTRY_PREFIX}velora-mcp-s4hana:latest" \
    -f "${SCRIPT_DIR}/ask-s4hana/Dockerfile" "${SCRIPT_DIR}/ask-s4hana"

# 3. SAP Analytics Cloud (SAC) MCP (Port 8084)
echo ""
echo "[3/6] Building SAC (SAP Analytics Cloud) image (Port 8084) for linux/amd64..."
docker build --platform linux/amd64 \
    -t "${REGISTRY_PREFIX}velora-mcp-sac:${TAG}" \
    -t "${REGISTRY_PREFIX}velora-mcp-sac:latest" \
    -f "${SCRIPT_DIR}/ask-sac/Dockerfile" "${SCRIPT_DIR}/ask-sac"

# 4. Productivity MCP (Port 8080)
echo ""
echo "[4/6] Building Productivity image (Port 8080) for linux/amd64..."
docker build --platform linux/amd64 \
    -t "${REGISTRY_PREFIX}velora-mcp-productivity:${TAG}" \
    -t "${REGISTRY_PREFIX}velora-mcp-productivity:latest" \
    -f "${SCRIPT_DIR}/ask-productivity/Dockerfile" "${SCRIPT_DIR}/ask-productivity"

# 5. Facilitator MCP (Port 8085)
echo ""
echo "[5/6] Building Facilitator image (Port 8085) for linux/amd64..."
docker build --platform linux/amd64 \
    -t "${REGISTRY_PREFIX}velora-mcp-facilitator:${TAG}" \
    -t "${REGISTRY_PREFIX}velora-mcp-facilitator:latest" \
    -f "${SCRIPT_DIR}/ask-facilitator/Dockerfile" "${SCRIPT_DIR}/ask-facilitator"

# 6. Dynamic Adaptive Card Service (Port 8086)
echo ""
echo "[6/6] Building Dynamic Adaptive Card Service image (Port 8086) for linux/amd64..."
docker build --platform linux/amd64 \
    -t "${REGISTRY_PREFIX}velora-mcp-card-service:${TAG}" \
    -t "${REGISTRY_PREFIX}velora-mcp-card-service:latest" \
    -f "${SCRIPT_DIR}/dynamic-adaptive-card-service/Dockerfile" "${SCRIPT_DIR}/dynamic-adaptive-card-service"

echo ""
echo "========================================="
echo "All 6 images built successfully for linux/amd64!"
echo " - ${REGISTRY_PREFIX}velora-mcp-sf:${TAG} & :latest (Port 8082)"
echo " - ${REGISTRY_PREFIX}velora-mcp-s4hana:${TAG} & :latest (Port 8083)"
echo " - ${REGISTRY_PREFIX}velora-mcp-sac:${TAG} & :latest (Port 8084)"
echo " - ${REGISTRY_PREFIX}velora-mcp-productivity:${TAG} & :latest (Port 8080)"
echo " - ${REGISTRY_PREFIX}velora-mcp-facilitator:${TAG} & :latest (Port 8085)"
echo " - ${REGISTRY_PREFIX}velora-mcp-card-service:${TAG} & :latest (Port 8086)"
echo "========================================="

if [ "$DO_PUSH" = true ] && [ -n "$REGISTRY" ]; then
    echo ""
    echo "========================================="
    echo "Pushing all 6 images to ACR and capturing immutable digests..."
    echo "========================================="

    IMAGES=(
        "velora-mcp-sf"
        "velora-mcp-s4hana"
        "velora-mcp-sac"
        "velora-mcp-productivity"
        "velora-mcp-facilitator"
        "velora-mcp-card-service"
    )

    > "$DIGESTS_FILE"

    for img in "${IMAGES[@]}"; do
        full_tag="${REGISTRY_PREFIX}${img}:${TAG}"
        latest_tag="${REGISTRY_PREFIX}${img}:latest"
        echo "Pushing ${full_tag}..."
        docker push "$full_tag"
        if [ "$full_tag" != "$latest_tag" ]; then
            echo "Pushing ${latest_tag}..."
            docker push "$latest_tag"
        fi
        
        # Extract immutable sha256 digest
        digest=$(docker inspect --format='{{index .RepoDigests 0}}' "$full_tag" 2>/dev/null || true)
        if [ -z "$digest" ]; then
            # fallback to docker images digest query
            digest=$(docker images --no-trunc --quiet "$full_tag" 2>/dev/null || true)
        fi
        
        var_name=$(echo "${img}" | tr '[:lower:]' '[:upper:]' | tr '-' '_')_DIGEST
        echo "${var_name}=\"${digest}\"" >> "$DIGESTS_FILE"
        echo " -> ${var_name}=${digest}"
    done

    echo ""
    echo "Immutable digest manifest recorded in: ${DIGESTS_FILE}"
elif [ -n "$REGISTRY" ]; then
    echo ""
    echo "To push all images to Azure Container Registry and capture immutable digests, run:"
    echo "  ./build_all_images.sh ${REGISTRY} ${TAG} --push"
fi

