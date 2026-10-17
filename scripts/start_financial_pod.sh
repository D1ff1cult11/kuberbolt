#!/usr/bin/env bash
# Start this agent's financial pod. Its gRPC port comes from network.grpc_port in the config.
# Config: $KUBERBOLT_HOME/$KUBERBOLT_AGENT/config.yaml (KUBERBOLT_HOME defaults to ~/.kuberbolt).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "${REPO_ROOT}/.env" ]; then set -a; source "${REPO_ROOT}/.env"; set +a; fi

: "${KUBERBOLT_AGENT:?Set KUBERBOLT_AGENT to the agent name}"
CONFIG="${KUBERBOLT_HOME:-$HOME/.kuberbolt}/${KUBERBOLT_AGENT}/config.yaml"
if [ ! -f "$CONFIG" ]; then
    echo "No config at $CONFIG. Run: kuberbolt init --name ${KUBERBOLT_AGENT} --role <client|merchant>, then fill in config.yaml." >&2
    exit 1
fi

cd "${REPO_ROOT}/agent-pod/financial-pod"
exec go run ./cmd/financialpod --config "$CONFIG"
