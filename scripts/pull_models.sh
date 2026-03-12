#!/usr/bin/env bash
# Pull Ollama models into the Docker volume using a helper container.
#
# Works from any machine — runs entirely inside Docker, so it respects
# DOCKER_HOST (local, ssh://ds1, or any other remote daemon).
#
# Use this instead of `ollama pull` when the Ollama container cannot reach the
# registry directly (e.g. IPv4-only firewall; curl works because it uses IPv6).
#
# Usage:
#   DOCKER_HOST=ssh://ds1 ./scripts/pull_models.sh
#   DOCKER_HOST=ssh://ds1 ./scripts/pull_models.sh nomic-embed-text
#   DOCKER_HOST=ssh://ds1 ./scripts/pull_models.sh nomic-embed-text llama3.1:8b
#
# Requirements: docker (with correct DOCKER_HOST set), no sudo needed.

set -euo pipefail

REGISTRY="registry.ollama.ai"
VOLUME="platform_ollama_data"
DEFAULT_MODELS=("nomic-embed-text" "llama3.1:8b")

if [ $# -eq 0 ]; then
    MODELS=("${DEFAULT_MODELS[@]}")
else
    MODELS=("$@")
fi

# Verify the volume exists on the target Docker host
docker volume inspect "$VOLUME" > /dev/null 2>&1 || {
    echo "Error: volume '$VOLUME' not found on Docker host '${DOCKER_HOST:-local}'." >&2
    echo "Run: docker compose -f infra/docker-compose.yml up -d" >&2
    exit 1
}

# ---------------------------------------------------------------------------
# Build the inner shell script that runs inside the helper container.
# The container mounts the ollama volume and uses curl to download blobs.
# ---------------------------------------------------------------------------

build_inner_script() {
    local input="$1"

    if [[ "$input" == *:* ]]; then
        local name="${input%%:*}"
        local tag="${input##*:}"
    else
        local name="$input"
        local tag="latest"
    fi

    cat <<INNER
set -e
apt-get update -qq && apt-get install -y --no-install-recommends curl -qq
REGISTRY="${REGISTRY}"
NAME="${name}"
TAG="${tag}"
BASE_DIR="/root/.ollama/models"
BLOBS="\$BASE_DIR/blobs"
MANIFEST_DIR="\$BASE_DIR/manifests/\$REGISTRY/library/\$NAME"
mkdir -p "\$BLOBS" "\$MANIFEST_DIR"

echo "  Fetching manifest for \$NAME:\$TAG..."
MANIFEST=\$(curl -sfL "https://\$REGISTRY/v2/library/\$NAME/manifests/\$TAG")
echo "\$MANIFEST" > "\$MANIFEST_DIR/\$TAG"

echo "\$MANIFEST" | python3 -c "
import json, sys
m = json.load(sys.stdin)
for item in [m['config']] + m.get('layers', []):
    print(item['digest'], item['size'])
" | while IFS=' ' read -r digest size; do
    filename="\${digest/sha256:/sha256-}"
    filepath="\$BLOBS/\$filename"
    if [ -f "\$filepath" ] && [ "\$(wc -c < "\$filepath")" -eq "\$size" ]; then
        echo "  Skipping \$filename (already complete)"
        continue
    fi
    mb=\$(( size / 1024 / 1024 ))
    echo "  Downloading \$filename (\${mb} MB)..."
    curl -L --progress-bar \\
        "https://\$REGISTRY/v2/library/\$NAME/blobs/\$digest" \\
        -o "\$filepath"
done
echo "  \$NAME:\$TAG ready"
INNER
}

# ---------------------------------------------------------------------------

for model in "${MODELS[@]}"; do
    echo ""
    echo "==> $model"

    inner_script=$(build_inner_script "$model")

    docker run --rm \
        -v "${VOLUME}:/root/.ollama" \
        python:3.11-slim \
        bash -c "$inner_script"
done

echo ""
echo "Verifying..."
docker exec platform-ollama-1 ollama list
