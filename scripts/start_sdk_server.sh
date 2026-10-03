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

# Ensure AGENT_FERNET_KEY is set
if [ -z "${AGENT_FERNET_KEY:-}" ]; then
    export AGENT_FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    echo "🔑 Generated ephemeral AGENT_FERNET_KEY for this session."
fi

export FRONTEND_ORIGIN="${FRONTEND_ORIGIN:-*}"
export DEFAULT_RELAYS="${DEFAULT_RELAYS:-wss://relay.damus.io,wss://nos.lol}"

echo "📡 Binding API server to 0.0.0.0:8000"
exec uvicorn api.main:app --host 0.0.0.0 --port 8000
