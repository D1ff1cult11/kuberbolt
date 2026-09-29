#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# generate_stubs.sh — Compile discovery.proto into Go and Python stubs.
#
# Run from the repo root:  bash agent-pod/proto/generate_stubs.sh
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROTO_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$PROTO_DIR/../.." && pwd)"

PROTO_FILE="$PROTO_DIR/discovery.proto"
GO_OUT="$REPO_ROOT/agent-pod/daemon/internal/pb"
PY_OUT="$REPO_ROOT/sdk/python"

echo "=== Proto directory : $PROTO_DIR"
echo "=== Go output       : $GO_OUT"
echo "=== Python output   : $PY_OUT"

# ── 0. Prerequisites ────────────────────────────────────────────────────────
# Ensure Go binaries (protoc-gen-go, protoc-gen-go-grpc) are in the PATH
export PATH="$PATH:$(go env GOPATH)/bin"

# Uncomment and run these once if the tools aren't already installed:
#
#   # protoc (macOS)
#   brew install protobuf
#
#   # Go plugins
#   go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
#   go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
#
#   # Python plugin (installs protoc-gen-grpc_python + grpcio-tools)
#   pip install grpcio-tools

# ── 1. Generate Go stubs ────────────────────────────────────────────────────
mkdir -p "$GO_OUT"

protoc \
  --proto_path="$PROTO_DIR" \
  --go_out="$GO_OUT" \
  --go_opt=paths=source_relative \
  --go-grpc_out="$GO_OUT" \
  --go-grpc_opt=paths=source_relative \
  "$PROTO_FILE"

echo "✓ Go stubs generated in $GO_OUT"

# ── 2. Generate Python stubs ────────────────────────────────────────────────
python -m grpc_tools.protoc \
  --proto_path="$PROTO_DIR" \
  --python_out="$PY_OUT" \
  --grpc_python_out="$PY_OUT" \
  "$PROTO_FILE"

echo "✓ Python stubs generated in $PY_OUT"
echo "=== Done."
