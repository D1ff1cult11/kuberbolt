# Machine C — SDK Server + Bitcoin Core (Linux)

## Your Role

You are the **infrastructure backbone**. Your machine runs:
- **Bitcoin Core** (regtest) — the shared blockchain that both LND nodes connect to
- **Redis** — session store for agent registration
- **FastAPI SDK Server** — registration, discovery, DM relay
- **React Frontend** — dashboard UI

You do **NOT** run any LND nodes. Each agent runs their own LND locally.

---

## Prerequisites

| Requirement | Check Command |
|-------------|---------------|
| Python 3.11+ | `python3 --version` |
| Docker | `docker --version` |
| Git | `git --version` |
| Node.js 18+ | `node --version` |

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/devlup-labs/kuberbolt.git
cd kuberbolt
git checkout dev && git pull origin dev
```

---

## Step 2: Get Your LAN IP

```bash
hostname -I | awk '{print $1}'
```

**Write this down** as `<MACHINE_C_IP>` — every other machine needs it.

---

## Step 3: Start Bitcoin Core

```bash
docker run -d --name bitcoind \
  -p 18443:18443 \
  -p 28332:28332 \
  -p 28333:28333 \
  lncm/bitcoind:v24.0 \
  -regtest=1 \
  -rpcallowip=0.0.0.0/0 \
  -rpcbind=0.0.0.0 \
  -rpcuser=devuser \
  -rpcpassword=devpass \
  -fallbackfee=0.0002 \
  -txindex=1 \
  -zmqpubrawblock=tcp://0.0.0.0:28332 \
  -zmqpubrawtx=tcp://0.0.0.0:28333

# Verify
docker exec bitcoind bitcoin-cli -regtest -rpcuser=devuser -rpcpassword=devpass getblockchaininfo
```

---

## Step 4: Start Redis

```bash
docker run -d --name kuberbolt-redis -p 6379:6379 redis:7-alpine
docker exec kuberbolt-redis redis-cli ping
# Expected: PONG
```

---

## Step 5: Setup Python Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install redis cryptography python-dotenv
```

---

## Step 6: Create `.env`

```bash
FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

cat > .env << EOF
FRONTEND_ORIGIN=*
DEFAULT_RELAYS=wss://relay.damus.io,wss://nos.lol
REDIS_URL=redis://localhost:6379/0
AGENT_FERNET_KEY=${FERNET_KEY}
KUBERBOLT_RELAYS=wss://relay.damus.io,wss://nos.lol
KUBERBOLT_HANDSHAKE_TIMEOUT_SECONDS=30
GOOGLE_API_KEY=
EOF
```

---

## Step 7: Start the SDK Server

```bash
source .venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Test: `curl http://localhost:8000/docs` — should show Swagger UI.

---

## Step 8: Start the Frontend (New Terminal)

```bash
cd frontend && npm install && npm run dev -- --host 0.0.0.0
```

Accessible at `http://<MACHINE_C_IP>:5173` from all machines.

---

## Step 9: Wait for Machine A and B to Start Their LND Nodes

Machine A (Alice) and Machine B (Bob) will each start their own LND Docker container that connects to YOUR bitcoind. You need to wait for them to finish before proceeding.

Once both are running, they will share:
- **Alice's LND pubkey** (from Machine A)
- **Bob's LND pubkey** (from Machine B)
- **Alice's wallet address** (for mining coins)

---

## Step 10: Mine Coins to Alice

Machine A will give you an Alice wallet address. Mine coins to it:

```bash
# Mine 101 blocks to Alice's address (coinbase maturity = 100)
docker exec bitcoind bitcoin-cli -regtest \
  -rpcuser=devuser -rpcpassword=devpass \
  generatetoaddress 101 <ALICE_ADDRESS_FROM_MACHINE_A>
```

---

## Step 11: Confirm the Channel

After Machine A opens the channel to Bob, mine 6 blocks to confirm it:

```bash
docker exec bitcoind bitcoin-cli -regtest \
  -rpcuser=devuser -rpcpassword=devpass \
  generatetoaddress 6 <ALICE_ADDRESS_FROM_MACHINE_A>
```

---

## Step 12: Register Both Agents

### Register Seller (for Machine B)

```bash
curl -s -X POST http://localhost:8000/api/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "role": "merchant",
    "display_name": "Kuberbolt Summarizer",
    "about": "AI text summarization powered by Gemini",
    "lightning": {
      "node_pubkey": "<BOB_LND_PUBKEY_FROM_MACHINE_B>",
      "lightning_address": "seller@regtest"
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

**Send the response** (`agent_pubkey`, `agent_privkey`, `session_token`) to Machine B.

### Register Buyer (for Machine A)

```bash
curl -s -X POST http://localhost:8000/api/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "role": "client",
    "display_name": "Kuberbolt Buyer Bot",
    "about": "Autonomous buyer agent",
    "lightning": {
      "node_pubkey": "<ALICE_LND_PUBKEY_FROM_MACHINE_A>",
      "lightning_address": "buyer@regtest"
    }
  }' | python3 -m json.tool
```

**Send the response** to Machine A.

> Note: `lightning_address` uses a dummy `@regtest` value since we're on regtest.

---

## What You Share With Teammates

| To Machine A (Windows) | To Machine B (macOS) |
|------------------------|---------------------|
| Your LAN IP (`<MACHINE_C_IP>`) | Your LAN IP (`<MACHINE_C_IP>`) |
| Buyer `agent_pubkey` | Seller `agent_pubkey` |
| Buyer `agent_privkey` | Seller `agent_privkey` |
| Buyer `session_token` | Seller `session_token` |

**You do NOT share any LND credentials.** Each machine has its own.

---

## Verification Checklist

- [ ] `docker exec bitcoind bitcoin-cli -regtest -rpcuser=devuser -rpcpassword=devpass getblockcount` returns > 107
- [ ] `docker exec kuberbolt-redis redis-cli ping` returns `PONG`
- [ ] `curl http://localhost:8000/docs` shows Swagger UI
- [ ] Frontend loads at `http://<MACHINE_C_IP>:5173`
- [ ] Both registrations returned successfully

---

## During the E2E Test

Mine a block every few minutes to keep the regtest chain moving:

```bash
# Keep mining in a loop (optional, helps with channel confirmations)
watch -n 60 "docker exec bitcoind bitcoin-cli -regtest -rpcuser=devuser -rpcpassword=devpass generatetoaddress 1 \$(docker exec bitcoind bitcoin-cli -regtest -rpcuser=devuser -rpcpassword=devpass getnewaddress)"
```
