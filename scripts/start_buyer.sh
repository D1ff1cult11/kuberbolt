#!/usr/bin/env bash
# ==============================================================================
# Kuberbolt — Start Buyer Agent (Machine A)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=================================================================="
echo "🚀 Starting Kuberbolt Buyer Agent (Machine A)"
echo "=================================================================="

# Check Python environment
if [ -d "${REPO_ROOT}/.venv" ]; then
    source "${REPO_ROOT}/.venv/bin/activate"
elif [ -d "${REPO_ROOT}/venv" ]; then
    source "${REPO_ROOT}/venv/bin/activate"
fi

if [ -z "${SDK_SERVER_URL:-}" ]; then
    echo "Enter SDK Server URL (Machine C) [e.g. http://192.168.1.50:8000]: "
    read -rp "SDK_SERVER_URL: " USER_SDK_URL
    export SDK_SERVER_URL="${USER_SDK_URL}"
fi

if [ -z "${BUYER_NOSTR_PRIVKEY:-}" ]; then
    echo "Enter BUYER_NOSTR_PRIVKEY (hex): "
    read -rp "BUYER_NOSTR_PRIVKEY: " USER_BUYER_KEY
    export BUYER_NOSTR_PRIVKEY="${USER_BUYER_KEY}"
fi

export PYTHONPATH="${REPO_ROOT}/agent-pod/brain:${REPO_ROOT}:${PYTHONPATH:-}"
export BUYER_FP_ADDR="${BUYER_FP_ADDR:-127.0.0.1:6001}"

PROMPT="${1:-Find a text summarization provider on the Kuberbolt network and use it to summarize this text: 'The Lightning Network is a payment channel network built on top of Bitcoin that enables instant, high-volume micropayments with minimal fees.'}"

echo ""
echo "Running Buyer Agent with prompt: \"$PROMPT\""
exec python3 -m app.buyer_agent "$PROMPT"
