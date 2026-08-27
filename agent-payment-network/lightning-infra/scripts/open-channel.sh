#!/usr/bin/env bash
# Automated local channel opener for two LND containers (regtest/local testing)
# Usage: adjust container names via env vars or run as-is if using the compose defaults.

set -euo pipefail

LND1=${LND1:-kuberbolt-lnd1}
LND2=${LND2:-kuberbolt-lnd2}
BITCOIND=${BITCOIND:-kuberbolt-bitcoind}
AMOUNT=${AMOUNT:-100000}
CONFIRM_BLOCKS=${CONFIRM_BLOCKS:-6}
TIMEOUT=${TIMEOUT:-120}

echo "Using LND1=${LND1}, LND2=${LND2}, BITCOIND=${BITCOIND}, AMOUNT=${AMOUNT} sats"

echo "1) Fetch identity pubkey from ${LND2}"
PUBKEY=$(docker exec -i "${LND2}" lncli getinfo | jq -r '.identity_pubkey')
if [ -z "${PUBKEY}" ] || [ "${PUBKEY}" = "null" ]; then
  echo "Failed to read pubkey from ${LND2}. Is the container running and wallet unlocked?"
  exit 1
fi
echo " -> pubkey: ${PUBKEY}"

echo "2) Connect ${LND1} -> ${LND2}"
docker exec -i "${LND1}" lncli connect "${PUBKEY}@${LND2}:9735" || true

echo "3) Open channel from ${LND1} to ${PUBKEY} (local_amt=${AMOUNT})"
docker exec -i "${LND1}" lncli openchannel --node_key="${PUBKEY}" --local_amt="${AMOUNT}" || true

echo "4) Mine ${CONFIRM_BLOCKS} blocks to confirm funding (regtest)"
docker exec -i "${BITCOIND}" bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpassword generate ${CONFIRM_BLOCKS}

echo "5) Wait for channel to become active (timeout ${TIMEOUT}s)"
end=$((SECONDS+TIMEOUT))
ACTIVE=false
while [ $SECONDS -lt $end ]; do
  ACTIVE=$(docker exec -i "${LND1}" lncli listchannels | jq -r --arg pk "${PUBKEY}" '.channels[]? | select(.remote_pubkey==$pk) | .active' || echo "false")
  if [ "${ACTIVE}" = "true" ]; then
    echo "Channel is active."
    break
  fi
  sleep 2
done

if [ "${ACTIVE}" != "true" ]; then
  echo "Channel not active after ${TIMEOUT}s. Check pending channels and confirmations."
  docker exec -i "${LND1}" lncli pendingchannels || true
  exit 2
fi

echo "6) Channel details:"
docker exec -i "${LND1}" lncli listchannels | jq -r --arg pk "${PUBKEY}" '.channels[]? | select(.remote_pubkey==$pk) | {remote_pubkey,channel_point,chan_id,balance,active}'

echo "Done. You can now create an invoice on the receiver and pay from the sender."
