#!/usr/bin/env bash
# ==============================================================================
# Kuberbolt — Start SDK & API Server (Machine C)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=================================================================="
echo "🚀 Starting Kuberbolt SDK / API Server (Machine C)"
echo "=================================================================="

# Check Python environment
if [ -d "${REPO_ROOT}/.venv" ]; then
    source "${REPO_ROOT}/.venv/bin/activate"
elif [ -d "${REPO_ROOT}/venv" ]; then
    source "${REPO_ROOT}/venv/bin/activate"
fi

# Load .env file if it exists
if [ -f "${REPO_ROOT}/.env" ]; then
    echo "📂 Loading environment variables from .env"
    set -a
    source "${REPO_ROOT}/.env"
    set +a
fi

# Ensure AGENT_FERNET_KEY is set
if [ -z "${AGENT_FERNET_KEY:-}" ]; then
    export AGENT_FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    echo "🔑 Generated ephemeral AGENT_FERNET_KEY for this session."
fi

# The key encrypts agent sessions in Redis and must survive restarts.
if [ -z "${AGENT_FERNET_KEY:-}" ]; then
    echo "AGENT_FERNET_KEY is required. Generate one with:"
    echo "  .venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
    exit 1
fi

export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export FRONTEND_ORIGIN="${FRONTEND_ORIGIN:-*}"
export DEFAULT_RELAYS="${DEFAULT_RELAYS:-wss://relay.damus.io,wss://nos.lol}"

echo "📡 Binding API server to 0.0.0.0:8000"
exec uvicorn api.main:app --host 0.0.0.0 --port 8000
