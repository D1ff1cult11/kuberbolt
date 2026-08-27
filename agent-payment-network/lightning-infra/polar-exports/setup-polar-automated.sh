#!/bin/bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   KUBERBOLT POLAR SETUP (Automated)    ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}\n"

# =======================
# STEP 1: Verify Polar Installation
# =======================

echo -e "${BLUE}Step 1: Checking Polar installation...${NC}"

if ! command -v polar &> /dev/null; then
    echo -e "${RED}✗ Polar not found. Install from: https://lightningpolar.com${NC}"
    exit 1
fi

POLAR_VERSION=$(polar --version 2>/dev/null || echo "unknown")
echo -e "${GREEN}✓ Polar found: $POLAR_VERSION${NC}\n"

# =======================
# STEP 2: Create Polar Network Configuration
# =======================

echo -e "${BLUE}Step 2: Creating Polar network...${NC}"

POLAR_CONFIG="${HOME}/.polar/networks/kuberbolt-regtest.json"
mkdir -p "${HOME}/.polar/networks"

cat > "$POLAR_CONFIG" << 'EOF'
{
  "id": "kuberbolt-regtest",
  "name": "Kuberbolt MVP (Regtest)",
  "lightning": [
    {
      "id": "alice",
      "name": "alice",
      "type": "lnd",
      "version": "v0.17.0",
      "ports": {
        "grpc": 10001,
        "rest": 8001
      }
    },
    {
      "id": "bob",
      "name": "bob",
      "type": "lnd",
      "version": "v0.17.0",
      "ports": {
        "grpc": 10002,
        "rest": 8002
      }
    },
    {
      "id": "charlie",
      "name": "charlie",
      "type": "lnd",
      "version": "v0.17.0",
      "ports": {
        "grpc": 10003,
        "rest": 8003
      }
    }
  ],
  "bitcoin": {
    "id": "bitcoind",
    "name": "bitcoind",
    "type": "bitcoind",
    "version": "26.0",
    "ports": {
      "rpc": 18443
    }
  },
  "connections": [
    {
      "lnds": ["alice", "bob"],
      "capacity": 10000000
    },
    {
      "lnds": ["bob", "charlie"],
      "capacity": 10000000
    }
  ]
}
EOF

echo -e "${GREEN}✓ Polar config created at: $POLAR_CONFIG${NC}\n"

# =======================
# STEP 3: Start Polar Network (Docker method)
# =======================

echo -e "${BLUE}Step 3: Starting Polar network via Docker...${NC}"

docker-compose -f polar/docker-compose.polar.yml up -d

sleep 5

echo -e "${GREEN}✓ Polar network started!${NC}\n"
