#!/bin/bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║    KUBERBOLT REGTEST INITIALIZER       ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}\n"

echo -e "${YELLOW}Waiting for bitcoind to start...${NC}"
sleep 5

# Create a wallet
docker exec kuberbolt-bitcoin bitcoin-cli -regtest -rpcuser=bitcoinrpc -rpcpassword=bitcoinrpc123 createwallet "default" || true

# Generate a new address
ADDRESS=$(docker exec kuberbolt-bitcoin bitcoin-cli -regtest -rpcuser=bitcoinrpc -rpcpassword=bitcoinrpc123 getnewaddress)

echo -e "${GREEN}✓ Wallet created. Mining 101 blocks to mature coinbase...${NC}"
docker exec kuberbolt-bitcoin bitcoin-cli -regtest -rpcuser=bitcoinrpc -rpcpassword=bitcoinrpc123 generatetoaddress 101 "$ADDRESS"

echo -e "${YELLOW}Waiting for LND nodes to sync...${NC}"
sleep 10

# Helper to run lncli inside containers
function lncli_exec() {
    CONTAINER=$1
    shift
    docker exec -i "$CONTAINER" lncli --network=regtest "$@"
}

echo -e "${BLUE}Step 1: Get LND identities...${NC}"
CLIENT_PUBKEY=$(lncli_exec kuberbolt-lnd-client getinfo | grep "identity_pubkey" | awk -F '"' '{print $4}')
PROV1_PUBKEY=$(lncli_exec kuberbolt-lnd-provider-1 getinfo | grep "identity_pubkey" | awk -F '"' '{print $4}')
PROV2_PUBKEY=$(lncli_exec kuberbolt-lnd-provider-2 getinfo | grep "identity_pubkey" | awk -F '"' '{print $4}')

echo "Client: $CLIENT_PUBKEY"
echo "Provider 1: $PROV1_PUBKEY"
echo "Provider 2: $PROV2_PUBKEY"

echo -e "\n${BLUE}Step 2: Funding LND nodes...${NC}"
CLIENT_ADDR=$(lncli_exec kuberbolt-lnd-client newaddress p2wkh | grep "address" | awk -F '"' '{print $4}')
PROV1_ADDR=$(lncli_exec kuberbolt-lnd-provider-1 newaddress p2wkh | grep "address" | awk -F '"' '{print $4}')
PROV2_ADDR=$(lncli_exec kuberbolt-lnd-provider-2 newaddress p2wkh | grep "address" | awk -F '"' '{print $4}')

docker exec kuberbolt-bitcoin bitcoin-cli -regtest -rpcuser=bitcoinrpc -rpcpassword=bitcoinrpc123 sendtoaddress "$CLIENT_ADDR" 1.0
docker exec kuberbolt-bitcoin bitcoin-cli -regtest -rpcuser=bitcoinrpc -rpcpassword=bitcoinrpc123 sendtoaddress "$PROV1_ADDR" 1.0
docker exec kuberbolt-bitcoin bitcoin-cli -regtest -rpcuser=bitcoinrpc -rpcpassword=bitcoinrpc123 sendtoaddress "$PROV2_ADDR" 1.0

# Mine blocks to confirm funding
docker exec kuberbolt-bitcoin bitcoin-cli -regtest -rpcuser=bitcoinrpc -rpcpassword=bitcoinrpc123 generatetoaddress 3 "$ADDRESS"
sleep 5

echo -e "\n${BLUE}Step 3: Connecting peers...${NC}"
# Connect client to prov1 and prov2
lncli_exec kuberbolt-lnd-client connect "${PROV1_PUBKEY}@kuberbolt-lnd-provider-1:9736" || true
lncli_exec kuberbolt-lnd-client connect "${PROV2_PUBKEY}@kuberbolt-lnd-provider-2:9736" || true
# Connect prov1 to prov2
lncli_exec kuberbolt-lnd-provider-1 connect "${PROV2_PUBKEY}@kuberbolt-lnd-provider-2:9736" || true
sleep 2

echo -e "\n${BLUE}Step 4: Opening channels (500k sats each)...${NC}"
lncli_exec kuberbolt-lnd-client openchannel --node_key="$PROV1_PUBKEY" --local_amt=500000 || true
lncli_exec kuberbolt-lnd-client openchannel --node_key="$PROV2_PUBKEY" --local_amt=500000 || true
lncli_exec kuberbolt-lnd-provider-1 openchannel --node_key="$PROV2_PUBKEY" --local_amt=500000 || true

# Mine blocks to confirm channels
docker exec kuberbolt-bitcoin bitcoin-cli -regtest -rpcuser=bitcoinrpc -rpcpassword=bitcoinrpc123 generatetoaddress 3 "$ADDRESS"
sleep 5

echo -e "\n${GREEN}✓ Regtest environment fully initialized!${NC}"
lncli_exec kuberbolt-lnd-client listchannels | grep -E "remote_pubkey|capacity"
