#!/usr/bin/env bash
# Run the buyer agent with a prompt: scripts/start_buyer.sh "<prompt>"
# Config: $KUBERBOLT_HOME/$KUBERBOLT_AGENT/config.yaml (KUBERBOLT_HOME defaults to ~/.kuberbolt).
set -euo pipefail

if [ $# -ne 1 ] || [ -z "$1" ]; then
    echo "Usage: $0 \"<prompt>\"" >&2
    exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "${REPO_ROOT}/.env" ]; then set -a; source "${REPO_ROOT}/.env"; set +a; fi

: "${KUBERBOLT_AGENT:?Set KUBERBOLT_AGENT to the agent name}"
CONFIG="${KUBERBOLT_HOME:-$HOME/.kuberbolt}/${KUBERBOLT_AGENT}/config.yaml"
if [ ! -f "$CONFIG" ]; then
    echo "No config at $CONFIG. Run: kuberbolt init --name ${KUBERBOLT_AGENT} --role client, then fill in config.yaml." >&2
    exit 1
fi

if [ -d "${REPO_ROOT}/.venv" ]; then source "${REPO_ROOT}/.venv/bin/activate"; fi
export PYTHONPATH="${REPO_ROOT}:${REPO_ROOT}/agent-pod/brain:${REPO_ROOT}/sdk/python:${PYTHONPATH:-}"
exec python3 -m app.buyer_agent "$1"
