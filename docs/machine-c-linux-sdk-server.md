# Machine C — SDK Server Setup Guide (Linux)

## Your Role

You are the **central infrastructure operator**. Your machine runs:
- **Bitcoin Core** (regtest) — the base blockchain
- **LND Alice** — buyer's Lightning node
- **LND Bob** — seller's Lightning node
- **Redis** — session store for agent registry
- **FastAPI SDK Server** — registration, discovery, DM relay, feedback
- **React Frontend** — dashboard UI

All other machines connect to your machine for LND access and API calls.

---

## Prerequisites

| Requirement | Check Command |
|-------------|---------------|
| Python 3.11+ | `python3 --version` |
| Docker & Docker Compose | `docker --version && docker compose version` |
| Git | `git --version` |
| Node.js 18+ (for frontend) | `node --version` |

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/devlup-labs/kuberbolt.git
cd kuberbolt
git checkout dev
git pull origin dev
```

---

## Step 2: Get Your LAN IP

```bash
hostname -I | awk '{print $1}'
```

Write this down — this is `<YOUR_IP>`. Share it with Machine A and Machine B.

---

## Step 3: Start Bitcoin Core + LND Nodes

```bash
cd lightning-infra
docker compose -f docker-compose.lnd.yml up -d
```

Wait 15 seconds, then verify all 3 containers are running:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected output:
```
NAMES       STATUS          PORTS
bitcoind    Up 15 seconds   0.0.0.0:18443->18443/tcp
alice       Up 15 seconds   0.0.0.0:10001->10009/tcp, 0.0.0.0:8081->8080/tcp
bob         Up 15 seconds   0.0.0.0:10002->10009/tcp, 0.0.0.0:8082->8080/tcp
```

---

## Step 4: Initialize the Lightning Network

### 4.1 Get Alice's wallet address and mine coins

```bash
# Get a fresh address from Alice
ALICE_ADDR=$(docker exec alice lncli --network=regtest newaddress p2wkh | python3 -c "import sys,json; print(json.load(sys.stdin)['address'])")
echo "Alice address: $ALICE_ADDR"

# Mine 101 blocks to Alice (coinbase maturity = 100 blocks)
docker exec bitcoind bitcoin-cli -regtest \
  -rpcuser=devuser -rpcpassword=devpass \
  generatetoaddress 101 $ALICE_ADDR
```

### 4.2 Verify Alice has funds

```bash
docker exec alice lncli --network=regtest walletbalance
```

You should see a non-zero `confirmed_balance` (roughly 50 BTC × number of blocks mined to her).

### 4.3 Get Bob's identity pubkey

```bash
BOB_PUBKEY=$(docker exec bob lncli --network=regtest getinfo | python3 -c "import sys,json; print(json.load(sys.stdin)['identity_pubkey'])")
echo "Bob's LND pubkey: $BOB_PUBKEY"
```

**Write this down** — Machine B needs it for their config.

### 4.4 Get Alice's identity pubkey

```bash
ALICE_PUBKEY=$(docker exec alice lncli --network=regtest getinfo | python3 -c "import sys,json; print(json.load(sys.stdin)['identity_pubkey'])")
echo "Alice's LND pubkey: $ALICE_PUBKEY"
```

**Write this down** — Machine A needs it for their config.

### 4.5 Connect Alice to Bob and open a channel

```bash
# Connect
docker exec alice lncli --network=regtest connect ${BOB_PUBKEY}@bob:9735

# Open channel with 500,000 sats capacity
docker exec alice lncli --network=regtest openchannel \
  --node_key=${BOB_PUBKEY} \
  --local_amt=500000

# Mine 6 blocks to confirm the channel
docker exec bitcoind bitcoin-cli -regtest \
  -rpcuser=devuser -rpcpassword=devpass \
  generatetoaddress 6 $ALICE_ADDR
```

### 4.6 Verify the channel is active

```bash
docker exec alice lncli --network=regtest listchannels
```

Look for `"active": true` and `"local_balance": "499817"` (or similar — slightly less than 500k due to fees).

---

## Step 5: Extract LND Credentials

Machine A needs Alice's creds. Machine B needs Bob's creds.

```bash
mkdir -p /tmp/kuberbolt-creds/alice /tmp/kuberbolt-creds/bob

# Alice's credentials (for Machine A — Windows Buyer)
docker cp alice:/root/.lnd/tls.cert /tmp/kuberbolt-creds/alice/tls.cert
docker cp alice:/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon /tmp/kuberbolt-creds/alice/admin.macaroon

# Bob's credentials (for Machine B — macOS Seller)
docker cp bob:/root/.lnd/tls.cert /tmp/kuberbolt-creds/bob/tls.cert
docker cp bob:/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon /tmp/kuberbolt-creds/bob/admin.macaroon

echo ""
echo "=========================================="
echo "  TRANSFER THESE FILES SECURELY"
echo "=========================================="
echo ""
echo "  → Send /tmp/kuberbolt-creds/alice/ to Machine A (Windows)"
echo "  → Send /tmp/kuberbolt-creds/bob/   to Machine B (macOS)"
echo ""
echo "  Use USB drive, scp, or AirDrop."
echo "  These files contain admin access to the Lightning nodes."
echo "=========================================="
```

---

## Step 6: Start Redis

```bash
docker run -d --name kuberbolt-redis \
  -p 6379:6379 \
  redis:7-alpine

# Verify Redis is running
docker exec kuberbolt-redis redis-cli ping
# Expected: PONG
```

---

## Step 7: Setup Python Environment

```bash
cd ~/kuberbolt  # or wherever you cloned

python3 -m venv .venv
source .venv/bin/activate

pip install -e .
pip install redis cryptography python-dotenv
```

---

## Step 8: Create the `.env` File

```bash
# Generate a Fernet encryption key
FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
echo "Generated Fernet key: $FERNET_KEY"

cat > .env << EOF
# SDK Server
FRONTEND_ORIGIN=*
DEFAULT_RELAYS=wss://relay.damus.io,wss://nos.lol

# Redis
REDIS_URL=redis://localhost:6379/0
AGENT_FERNET_KEY=${FERNET_KEY}

# Nostr
KUBERBOLT_RELAYS=wss://relay.damus.io,wss://nos.lol
KUBERBOLT_HANDSHAKE_TIMEOUT_SECONDS=30

# Gemini (optional on SDK server)
GOOGLE_API_KEY=
EOF

echo "Created .env file"
```

---

## Step 9: Start the SDK Server

```bash
source .venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Started reloader process
```

Test it from another machine:
```
curl http://<YOUR_IP>:8000/health
# Expected: {"status":"ok"}
```

---

## Step 10: Start the Frontend (New Terminal)

```bash
cd ~/kuberbolt/frontend
npm install
npm run dev -- --host 0.0.0.0
```

The frontend is now accessible at `http://<YOUR_IP>:5173` from all machines.

---

## Step 11: Register Both Agents

### 11.1 Register the Seller (for Machine B)

```bash
curl -s -X POST http://localhost:8000/api/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "role": "merchant",
    "display_name": "Kuberbolt Summarizer",
    "about": "AI text summarization powered by Gemini",
    "lightning": {
      "node_pubkey": "'${BOB_PUBKEY}'"
    },
    "service": {
      "service_name": "Text Summarization",
      "service_description": "Summarize text using Google Gemini",
      "category": "text-summarization",
      "price_sats": 100,
      "price_unit": "per_request"
    }
  }' | python3 -m json.tool
```

**Save the entire response.** Send these values to Machine B:
- `agent_pubkey`
- `agent_privkey` (if returned) or the hex private key
- `session_token`

### 11.2 Register the Buyer (for Machine A)

```bash
curl -s -X POST http://localhost:8000/api/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "role": "client",
    "display_name": "Kuberbolt Buyer Bot",
    "about": "Autonomous buyer agent",
    "lightning": {
      "node_pubkey": "'${ALICE_PUBKEY}'"
    }
  }' | python3 -m json.tool
```

**Save the entire response.** Send these values to Machine A:
- `agent_pubkey`
- `agent_privkey` (if returned) or the hex private key
- `session_token`

---

## What You Need to Share With Teammates

### Send to Machine A (Windows — Buyer):

| Item | Value |
|------|-------|
| Your LAN IP | `<YOUR_IP>` |
| Alice TLS cert | `/tmp/kuberbolt-creds/alice/tls.cert` |
| Alice admin macaroon | `/tmp/kuberbolt-creds/alice/admin.macaroon` |
| Alice LND pubkey | `$ALICE_PUBKEY` |
| Buyer agent_pubkey | From registration response |
| Buyer agent_privkey | From registration response |
| Buyer session_token | From registration response |

### Send to Machine B (macOS — Seller):

| Item | Value |
|------|-------|
| Your LAN IP | `<YOUR_IP>` |
| Bob TLS cert | `/tmp/kuberbolt-creds/bob/tls.cert` |
| Bob admin macaroon | `/tmp/kuberbolt-creds/bob/admin.macaroon` |
| Bob LND pubkey | `$BOB_PUBKEY` |
| Seller agent_pubkey | From registration response |
| Seller agent_privkey | From registration response |
| Seller session_token | From registration response |

---

## Verification Checklist

- [ ] `docker ps` shows `bitcoind`, `alice`, `bob`, `kuberbolt-redis` all running
- [ ] `docker exec alice lncli --network=regtest listchannels` shows active channel
- [ ] `curl http://localhost:8000/health` returns `{"status":"ok"}`
- [ ] `docker exec kuberbolt-redis redis-cli ping` returns `PONG`
- [ ] Frontend loads at `http://<YOUR_IP>:5173`
- [ ] Both agent registrations returned pubkeys successfully
- [ ] LND credential files copied and sent to teammates

---

## Keeping Things Running

If Docker containers stop (e.g. after reboot):

```bash
# Restart everything
cd ~/kuberbolt/lightning-infra
docker compose -f docker-compose.lnd.yml start
docker start kuberbolt-redis

# Check channel is still active
docker exec alice lncli --network=regtest listchannels
```

If the channel balance runs out during testing, fund Alice again:

```bash
ALICE_ADDR=$(docker exec alice lncli --network=regtest newaddress p2wkh | python3 -c "import sys,json; print(json.load(sys.stdin)['address'])")
docker exec bitcoind bitcoin-cli -regtest -rpcuser=devuser -rpcpassword=devpass generatetoaddress 10 $ALICE_ADDR
```
