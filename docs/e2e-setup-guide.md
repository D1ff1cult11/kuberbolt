# Kuberbolt End-to-End Setup Guide

## Multi-Machine Deployment (3 Devices)

| Machine | OS | Role | What It Runs |
|---------|-----|------|-------------|
| **Machine A** | Windows | Buyer Agent | LND Node (Alice) + Go Financial Pod + LangChain Buyer Agent |
| **Machine B** | macOS | Seller Agent | LND Node (Bob) + Go Financial Pod + Seller Brain (Gemini compute + NIP-44 listener) |
| **Machine C** | Linux | SDK Server | FastAPI API + Redis + React Frontend + Bitcoin Core (regtest) |

> **All 3 machines must be on the same WiFi/LAN network.**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        NOSTR RELAYS                                 │
│              wss://relay.damus.io   wss://nos.lol                   │
│    kind:0 (Profile)  kind:31990 (Service)  NIP-44 (DMs)  kind:7000 │
└──────┬──────────────────────┬────────────────────────┬──────────────┘
       │                      │                        │
┌──────▼──────────┐   ┌──────▼──────────┐   ┌────────▼────────────┐
│  MACHINE C      │   │  MACHINE A      │   │  MACHINE B          │
│  Linux (SDK)    │   │  Windows (Buyer)│   │  macOS (Seller)     │
│                 │   │                 │   │                     │
│  FastAPI :8000  │   │  LND Alice      │   │  LND Bob            │
│  Redis   :6379  │   │    gRPC :10009  │   │    gRPC :10009      │
│  Frontend:5173  │   │                 │   │                     │
│  Bitcoin :18443 │   │  Financial Pod  │   │  Financial Pod      │
│                 │   │    gRPC :6001   │   │    gRPC :6001       │
│                 │   │                 │   │                     │
│                 │   │  Buyer Agent    │   │  Seller Brain :8001 │
│                 │   │  (LangChain)    │   │  (Gemini + NIP-44)  │
└─────────────────┘   └────────┬────────┘   └─────────┬───────────┘
                               │      gRPC L402       │
                               └──────────────────────┘
                                  HODL Invoice Flow
                               Alice ──Lightning──▶ Bob
```

---

## Prerequisites (All Machines)

- [ ] Python 3.11+
- [ ] Docker & Docker Compose
- [ ] Git
- [ ] Note each machine's LAN IP address

**Machine A (Windows) additional:**
- [ ] Go 1.21+
- [ ] `grpcurl` (optional, for debugging)

**Machine B (macOS) additional:**
- [ ] Go 1.21+
- [ ] Google API Key (for Gemini AI summarization)

---

## Step-by-Step Deployment

---

### Phase 0: Get Machine LAN IPs

Run on each machine and write down the IP:

**Windows (Machine A):**
```powershell
(Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias Wi-Fi).IPAddress
```

**macOS (Machine B):**
```bash
ipconfig getifaddr en0
```

**Linux (Machine C):**
```bash
hostname -I | awk '{print $1}'
```

Throughout this guide, replace:
- `<MACHINE_A_IP>` with the Windows machine's LAN IP (e.g. `192.168.1.10`)
- `<MACHINE_B_IP>` with the macOS machine's LAN IP (e.g. `192.168.1.11`)
- `<MACHINE_C_IP>` with the Linux machine's LAN IP (e.g. `192.168.1.12`)

---

### Phase 1: Machine C (Linux) — SDK Server + Bitcoin Infrastructure

Machine C runs the central SDK server, Redis, and a shared Bitcoin Core node for regtest.

#### 1.1 Clone and Setup

```bash
git clone https://github.com/devlup-labs/kuberbolt.git
cd kuberbolt
git checkout dev && git pull origin dev

# Create Python venv
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install redis cryptography
```

#### 1.2 Create `.env`

```bash
cat > .env << 'EOF'
# SDK Server Config
FRONTEND_ORIGIN=*
DEFAULT_RELAYS=wss://relay.damus.io,wss://nos.lol

# Redis (for agent session registry)
REDIS_URL=redis://localhost:6379/0
AGENT_FERNET_KEY=<GENERATE_WITH_COMMAND_BELOW>

# Gemini (optional on SDK server)
GOOGLE_API_KEY=
EOF
```

Generate the Fernet key:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Paste the output as `AGENT_FERNET_KEY` value in `.env`.

#### 1.3 Start Redis

```bash
docker run -d --name kuberbolt-redis -p 6379:6379 redis:7-alpine
```

Verify:
```bash
docker exec kuberbolt-redis redis-cli ping
# Expected: PONG
```

#### 1.4 Start Bitcoin Core + LND Nodes (Regtest)

```bash
cd lightning-infra
docker compose -f docker-compose.lnd.yml up -d
```

Wait 10-15 seconds for containers to start, then verify:
```bash
docker ps
# Should show: bitcoind, alice, bob
```

#### 1.5 Initialize Lightning Network

```bash
# Mine 101 blocks so Alice has spendable coins
docker exec bitcoind bitcoin-cli -regtest -rpcuser=devuser -rpcpassword=devpass generatetoaddress 101 $(docker exec alice lncli --network=regtest newaddress p2wkh | grep address | cut -d'"' -f4)

# Wait 5 seconds for sync
sleep 5

# Verify Alice has funds
docker exec alice lncli --network=regtest walletbalance
# Should show non-zero confirmed_balance

# Get Bob's identity pubkey
BOB_PUBKEY=$(docker exec bob lncli --network=regtest getinfo | grep identity_pubkey | cut -d'"' -f4)
echo "Bob's pubkey: $BOB_PUBKEY"

# Connect Alice to Bob
docker exec alice lncli --network=regtest connect ${BOB_PUBKEY}@bob:9735

# Open channel (500,000 sats)
docker exec alice lncli --network=regtest openchannel --node_key=${BOB_PUBKEY} --local_amt=500000

# Mine 6 blocks to confirm channel
docker exec bitcoind bitcoin-cli -regtest -rpcuser=devuser -rpcpassword=devpass generatetoaddress 6 $(docker exec alice lncli --network=regtest newaddress p2wkh | grep address | cut -d'"' -f4)

# Verify channel is active
docker exec alice lncli --network=regtest listchannels
# Should show active: true
```

#### 1.6 Copy LND Credentials for Remote Machines

The buyer (Machine A) needs Alice's creds, and the seller (Machine B) needs Bob's creds.

```bash
# Create a temp directory with the creds
mkdir -p /tmp/kuberbolt-creds/alice /tmp/kuberbolt-creds/bob

# Copy Alice's TLS cert and admin macaroon
docker cp alice:/root/.lnd/tls.cert /tmp/kuberbolt-creds/alice/tls.cert
docker cp alice:/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon /tmp/kuberbolt-creds/alice/admin.macaroon

# Copy Bob's TLS cert and admin macaroon
docker cp bob:/root/.lnd/tls.cert /tmp/kuberbolt-creds/bob/tls.cert
docker cp bob:/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon /tmp/kuberbolt-creds/bob/admin.macaroon

echo "=== Transfer these files ==="
echo "Send /tmp/kuberbolt-creds/alice/ → Machine A (Windows)"
echo "Send /tmp/kuberbolt-creds/bob/   → Machine B (macOS)"
```

> **Transfer these files** to the respective machines via USB, SCP, or any secure method.
> Machine A needs: `alice/tls.cert` + `alice/admin.macaroon`
> Machine B needs: `bob/tls.cert` + `bob/admin.macaroon`

#### 1.7 Start the SDK Server

```bash
cd ~/kuberbolt  # back to repo root
source .venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

#### 1.8 Start the Frontend (Optional — for Registration UI)

Open a **new terminal**:
```bash
cd ~/kuberbolt/frontend
npm install
npm run dev -- --host 0.0.0.0
```

The frontend is now accessible from all machines at `http://<MACHINE_C_IP>:5173`.

---

### Phase 2: Agent Registration

Register both agents using **curl** from Machine C (or any machine).

#### 2.1 Register Seller Agent (Machine B)

```bash
curl -s -X POST http://<MACHINE_C_IP>:8000/api/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "role": "merchant",
    "display_name": "Kuberbolt Summarizer",
    "about": "AI text summarization powered by Gemini",
    "lightning": {
      "node_pubkey": "<BOB_LND_PUBKEY>"
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

**Save the response.** You need:
- `agent_pubkey` → Seller's Nostr public key
- `agent_privkey` → Seller's Nostr private key (hex)
- `session_token` → Bearer token for authenticated API calls

#### 2.2 Register Buyer Agent (Machine A)

```bash
curl -s -X POST http://<MACHINE_C_IP>:8000/api/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "role": "client",
    "display_name": "Kuberbolt Buyer Bot",
    "about": "Autonomous buyer agent",
    "lightning": {
      "node_pubkey": "<ALICE_LND_PUBKEY>"
    }
  }' | python3 -m json.tool
```

**Save the response.** You need:
- `agent_pubkey` → Buyer's Nostr public key
- `agent_privkey` → Buyer's Nostr private key (hex)
- `session_token` → Bearer token

---

### Phase 3: Machine B (macOS) — Seller Stack

#### 3.1 Clone and Setup

```bash
git clone https://github.com/devlup-labs/kuberbolt.git
cd kuberbolt
git checkout dev && git pull origin dev
```

#### 3.2 Place LND Credentials

Copy the `bob/tls.cert` and `bob/admin.macaroon` files you transferred from Machine C:

```bash
mkdir -p kuberbolt-config
cp /path/to/bob/tls.cert kuberbolt-config/tls.cert
cp /path/to/bob/admin.macaroon kuberbolt-config/admin.macaroon
```

#### 3.3 Create Seller Financial Pod Config

```bash
cat > kuberbolt-config/seller.yaml << EOF
agent:
  name: seller
  role: provider
  nostr_npub: "<SELLER_AGENT_PUBKEY_FROM_REGISTRATION>"
  nostr_priv_key: "<SELLER_AGENT_PRIVKEY_FROM_REGISTRATION>"
  created_at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
services:
  - name: text-summarization
    kind: 0
    description: Summarize text using Gemini AI
    price_msat: 100000
    timeout_sec: 60
network:
  grpc_port: 6001
  public_host: 0.0.0.0
  nostr_relays: []
brain:
  url: http://127.0.0.1:8001
lightning:
  network: regtest
  lnd_host: <MACHINE_C_IP>
  lnd_grpc_port: 10002
  tls_cert_path: $(pwd)/kuberbolt-config/tls.cert
  macaroon_path: $(pwd)/kuberbolt-config/admin.macaroon
budget:
  daily_limit_msat: 100000000
  monthly_limit_msat: 3000000000
logging:
  level: info
  format: console
EOF
```

> **Key detail:** `lnd_host` points to Machine C because that's where Bob's LND Docker container is running. `lnd_grpc_port: 10002` matches Bob's mapped port.

#### 3.4 Build and Start the Go Financial Pod

```bash
cd agent-pod/financial-pod
go build -o financialpod ./cmd/financialpod
./financialpod --config ../../kuberbolt-config/seller.yaml
```

You should see:
```
INFO  gRPC server listening  addr=0.0.0.0:6001
INFO  connected to LND       alias=bob  synced=true
```

#### 3.5 Start the Seller Brain

Open a **new terminal**:
```bash
cd kuberbolt/agent-pod/brain
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create .env for the brain
cat > .env << EOF
SELLER_NOSTR_PRIVKEY=<SELLER_AGENT_PRIVKEY_FROM_REGISTRATION>
GOOGLE_API_KEY=<YOUR_GEMINI_API_KEY>
KUBERBOLT_RELAYS=wss://relay.damus.io,wss://nos.lol
BRAIN_HOST=0.0.0.0
BRAIN_PORT=8001
FP_GRPC_PORT=6001
EOF

python3 -m app.seller_agent
```

You should see:
```
🚀 KUBERBOLT SELLER AGENT (Machine B)
Local LAN IP: 192.168.x.y
Compute Server: http://0.0.0.0:8001
Listening for resolve_endpoint handshake requests...
```

---

### Phase 4: Machine A (Windows) — Buyer Stack

#### 4.1 Clone and Setup

```powershell
git clone https://github.com/devlup-labs/kuberbolt.git
cd kuberbolt
git checkout dev; git pull origin dev
```

#### 4.2 Place LND Credentials

Copy the `alice/tls.cert` and `alice/admin.macaroon` files from Machine C:

```powershell
mkdir kuberbolt-config -Force
# Copy alice/tls.cert and alice/admin.macaroon into kuberbolt-config/
```

#### 4.3 Create Buyer Financial Pod Config

Create `kuberbolt-config/buyer.yaml`:
```yaml
agent:
  name: buyer
  role: client
  nostr_npub: "<BUYER_AGENT_PUBKEY_FROM_REGISTRATION>"
  nostr_priv_key: "<BUYER_AGENT_PRIVKEY_FROM_REGISTRATION>"
  created_at: "2026-10-04T00:00:00Z"
services: []
network:
  grpc_port: 6001
  public_host: 0.0.0.0
  nostr_relays: []
brain:
  url: http://127.0.0.1:9999
lightning:
  network: regtest
  lnd_host: <MACHINE_C_IP>
  lnd_grpc_port: 10001
  tls_cert_path: D:/path/to/kuberbolt/kuberbolt-config/tls.cert
  macaroon_path: D:/path/to/kuberbolt/kuberbolt-config/admin.macaroon
budget:
  daily_limit_msat: 100000000
  monthly_limit_msat: 3000000000
logging:
  level: info
  format: console
```

> **Key detail:** `lnd_host` points to Machine C. `lnd_grpc_port: 10001` matches Alice's mapped port.

#### 4.4 Build and Start the Go Financial Pod

```powershell
cd agent-pod\financial-pod
go build -o financialpod.exe .\cmd\financialpod
.\financialpod.exe --config ..\..\kuberbolt-config\buyer.yaml
```

You should see:
```
INFO  gRPC server listening  addr=0.0.0.0:6001
INFO  connected to LND       alias=alice  synced=true
```

#### 4.5 Run the Buyer Agent

Open a **new terminal**:
```powershell
cd kuberbolt\agent-pod\brain
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Set environment variables
$env:SDK_SERVER_URL = "http://<MACHINE_C_IP>:8000"
$env:BUYER_NOSTR_PUBKEY = "<BUYER_AGENT_PUBKEY_FROM_REGISTRATION>"
$env:BUYER_SESSION_TOKEN = "<BUYER_SESSION_TOKEN_FROM_REGISTRATION>"
$env:BUYER_FP_ADDR = "127.0.0.1:6001"
$env:GOOGLE_API_KEY = "<YOUR_GEMINI_API_KEY>"

python -m app.buyer_agent "Find a text summarization provider on the Kuberbolt network and use it to summarize this text: 'The Lightning Network is a payment channel network built on top of Bitcoin. It enables instant, low-fee transactions by routing payments through bidirectional payment channels secured by Hash Time-Locked Contracts.'"
```

---

### Phase 5: Verify End-to-End Success

After running the buyer agent, you should observe this sequence across all 3 machines:

#### On Machine A (Windows — Buyer):
```
Running agent with prompt: Find a text summarization provider...
Thought: I need to discover providers first
Action: discover_providers
Observation: [{service_name: "Text Summarization", agent_pubkey: "..."}]
Action: request_endpoint
Observation: {host: "192.168.x.y", port: 6001}
Action: call_service
Observation: {"summary": "The Lightning Network enables..."}
Action: publish_feedback
Final Answer: Successfully summarized the text!
```

#### On Machine B (macOS — Seller):
```
⚡ [L402 CHALLENGE] Invoice created for Buyer -> Amount: 100 sats
╔══════════════════════════════════════════════════╗
║ 🔒 HTLC LOCKED — BUYER PAYMENT RECEIVED         ║
║  Status: Executing AI Compute...                 ║
╚══════════════════════════════════════════════════╝
Processing compute job (input length: 245 chars)...
╔══════════════════════════════════════════════════╗
║ 💰 PAYMENT SETTLED — FUNDS CLAIMED               ║
╚══════════════════════════════════════════════════╝
```

#### On Machine C (Linux — SDK Server):
```
INFO Incoming Request: GET /api/providers?category=text-summarization
INFO Incoming Request: POST /api/requests Body: {action: resolve_endpoint}
INFO Incoming Request: POST /api/feedback Body: {rating: 5}
```

---

## Verification Checklist

- [ ] Bitcoin Core running (regtest, port 18443)
- [ ] Alice LND synced to chain (`synced_to_chain: true`)
- [ ] Bob LND synced to chain
- [ ] Channel open between Alice ↔ Bob (>0 local balance on Alice side)
- [ ] Redis running (port 6379)
- [ ] FastAPI server accepting requests (port 8000)
- [ ] Frontend accessible at `http://<MACHINE_C_IP>:5173`
- [ ] Seller registered on Nostr (kind:0 + kind:31990)
- [ ] Buyer registered on Nostr (kind:0)
- [ ] Seller Financial Pod connected to Bob LND via gRPC
- [ ] Seller Brain listening for NIP-44 DMs
- [ ] Seller Brain compute endpoint healthy (`curl http://localhost:8001/health`)
- [ ] Buyer Financial Pod connected to Alice LND via gRPC
- [ ] Buyer agent discovers seller via `/api/providers`
- [ ] NIP-44 DM exchange resolves seller endpoint
- [ ] L402 challenge issued (HODL invoice + macaroon)
- [ ] HTLC locked (buyer pays)
- [ ] Compute executed (Gemini summarization)
- [ ] Invoice settled (preimage revealed)
- [ ] Output returned to buyer
- [ ] Feedback published as kind:7000

---

## Troubleshooting

### "LND connection failed"
- Verify the LND container is running: `docker ps`
- Verify the TLS cert and macaroon paths are correct
- Verify `lnd_host` in config points to Machine C's LAN IP
- Verify ports 10001/10002 are not blocked by firewall

### "Redis connection refused"
- Start Redis: `docker run -d --name kuberbolt-redis -p 6379:6379 redis:7-alpine`
- Set `REDIS_URL=redis://localhost:6379/0` in `.env`

### "SELLER_NOSTR_PRIVKEY is not set"
- The seller brain needs the private key from registration
- Set it in `agent-pod/brain/.env` or export as env variable

### "Channel not found / insufficient balance"
- Mine more blocks: `docker exec bitcoind bitcoin-cli -regtest -rpcuser=devuser -rpcpassword=devpass generatetoaddress 10 <alice_address>`
- Verify channel: `docker exec alice lncli --network=regtest listchannels`

### "Nostr DM not received"
- Increase timeout: `KUBERBOLT_HANDSHAKE_TIMEOUT_SECONDS=60`
- Verify relays are reachable: `wscat -c wss://relay.damus.io`
- Both agents must use the same relay list

### "Compute failed / Gemini error"
- Verify `GOOGLE_API_KEY` is set and valid
- The seller brain falls back to local summarization if Gemini is unavailable
