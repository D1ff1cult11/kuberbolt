#!/usr/bin/env bash
# Peer setup helper (copy-paste and run manually on each user's host).
# This script is a guide and will not be executed by the assistant.

set -euo pipefail

# Configure these variables before running
CONTAINER_NAME=${CONTAINER_NAME:-kuberbolt-lnd}
BITCOIND_CONTAINER=${BITCOIND_CONTAINER:-kuberbolt-bitcoind}
BITCOIND_RPC_USER=${BITCOIND_RPC_USER:-rpcuser}
BITCOIND_RPC_PASS=${BITCOIND_RPC_PASS:-rpcpassword}
REGTEST_MINED_BLOCKS=${REGTEST_MINED_BLOCKS:-101}

echo "1) Create LND wallet (interactive step)."
echo "   Run inside the LND container: docker exec -it ${CONTAINER_NAME} lncli create"

echo
echo "2) Generate regtest blocks (if using shared bitcoind) to get spendable coins:"
echo "   docker exec -it ${BITCOIND_CONTAINER} bitcoin-cli -regtest -rpcuser=${BITCOIND_RPC_USER} -rpcpassword=${BITCOIND_RPC_PASS} generate ${REGTEST_MINED_BLOCKS}"

echo
echo "3) Get an on-chain address from LND and fund it (example):"
echo "   ADDR=$(docker exec -it ${CONTAINER_NAME} lncli newaddress p2wkh | jq -r '.address')"
echo "   docker exec -it ${BITCOIND_CONTAINER} bitcoin-cli -regtest -rpcuser=${BITCOIND_RPC_USER} -rpcpassword=${BITCOIND_RPC_PASS} sendtoaddress \$ADDR 1"
echo "   docker exec -it ${BITCOIND_CONTAINER} bitcoin-cli -regtest -rpcuser=${BITCOIND_RPC_USER} -rpcpassword=${BITCOIND_RPC_PASS} generate 6"

echo
echo "4) Exchange peer info (on each node):"
echo "   docker exec -it ${CONTAINER_NAME} lncli getinfo    # copy identity_pubkey and reachable addresses"

echo
echo "5) Connect to peer (run on one node):"
echo "   docker exec -it ${CONTAINER_NAME} lncli connect <pubkey>@<host>:9735"

echo
echo "6) Open channel from the initiator (example 100k sats):"
echo "   docker exec -it ${CONTAINER_NAME} lncli openchannel --node_key=<pubkey> --local_amt=100000"

echo
echo "7) Check channel status:
docker exec -it ${CONTAINER_NAME} lncli listchannels
docker exec -it ${CONTAINER_NAME} lncli pendingchannels"

echo
echo "8) Create invoice on receiver and pay from sender (example):"
echo "   docker exec -it <receiver_container> lncli addinvoice --amt=1000"
echo "   docker exec -it <sender_container> lncli payinvoice <payment_request>"

echo
echo "Notes: Adjust container names, host addresses, and amounts as needed. Securely backup seeds and macaroons."
