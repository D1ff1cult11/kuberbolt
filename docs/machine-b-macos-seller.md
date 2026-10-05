# Machine B — Seller Agent Setup Guide (macOS)

## Your Role

You are the **seller agent operator**. Your machine runs:
- **Bob LND Node** (Docker) — your own Lightning wallet, connected to Machine C's bitcoind
- **Go Financial Pod** — issues L402 challenges, holds HODL invoices, settles after compute
- **Seller Brain** — FastAPI compute server (Gemini AI) + NIP-44 endpoint resolver

**Your LND credentials never leave this machine.**

---

## What You Need

| From Machine C | What It Is |
|---------------|-----------|
| **Machine C IP** | LAN IP (e.g. `192.168.1.12`) |
| **Seller `agent_pubkey`** | From registration response |
| **Seller `agent_privkey`** | From registration response |
| **Seller `session_token`** | From registration response |

| From Machine A | What It Is |
|---------------|-----------|
| **Machine A IP** | LAN IP of buyer machine |
| **Alice LND pubkey** | For channel verification |

| You Need | Where to Get It |
|----------|----------------|
| **Google API Key** | https://aistudio.google.com/apikey |

---

## Prerequisites

| Requirement | Check Command |
|-------------|---------------|
| Python 3.11+ | `python3 --version` |
| Go 1.21+ | `go version` |
| Docker Desktop | `docker --version` |
| Git | `git --version` |

```bash
# Install Go if needed
brew install go
```

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
ipconfig getifaddr en0
```

Write this down as `<MACHINE_B_IP>`. Share with Machine A (for Lightning channel + gRPC).

---

## Step 3: Start Bob LND (Docker)

Bob connects to Machine C's bitcoind over the LAN. Replace `<MACHINE_C_IP>`.

```bash
docker run -d --name bob \
  -p 10009:10009 -p 8080:8080 -p 9735:9735 \
  -v $(pwd)/bob-data:/root/.lnd \
  lightninglabs/lnd:v0.17.4-beta \
  --noseedbackup \
  --trickledelay=5000 \
  --alias=bob \
  --bitcoin.active \
  --bitcoin.regtest \
  --bitcoin.node=bitcoind \
  --bitcoind.rpchost=<MACHINE_C_IP>:18443 \
  --bitcoind.rpcuser=devuser \
  --bitcoind.rpcpass=devpass \
  --bitcoind.zmqpubrawblock=tcp://<MACHINE_C_IP>:28332 \
  --bitcoind.zmqpubrawtx=tcp://<MACHINE_C_IP>:28333 \
  --rpclisten=0.0.0.0:10009 \
  --restlisten=0.0.0.0:8080 \
  --listen=0.0.0.0:9735 \
  --tlsextradomain=localhost
```

Wait 10 seconds, then verify:

```bash
docker exec bob lncli --network=regtest getinfo
```

**Write down Bob's LND pubkey** (`identity_pubkey`) and share it with Machine A and Machine C.

---

## Step 4: Wait for Channel

Machine A (Alice) will open a Lightning channel to your Bob node. After Machine C mines the confirmation blocks, verify:

```bash
docker exec bob lncli --network=regtest listchannels
# Should show "active": true with remote_balance > 0
```

The `remote_balance` is Alice's funds that she can pay you with.

---

## Step 5: Create Seller Financial Pod Config

```bash
mkdir -p kuberbolt-config
cat > kuberbolt-config/seller.yaml << 'EOF'
agent:
  name: seller
  role: provider
  nostr_npub: "<SELLER_AGENT_PUBKEY>"
  nostr_priv_key: "<SELLER_AGENT_PRIVKEY>"
  created_at: "2026-10-05T00:00:00Z"
services:
  - name: text-summarization
    kind: 0
    description: Summarize text using Gemini AI
    price_msat: 100000
    timeout_sec: 60
network:
  grpc_port: 6001
  public_host: 0.0.0.0
  nostr_relays:
    - wss://relay.damus.io
    - wss://nos.lol
brain:
  url: http://127.0.0.1:8001
lightning:
  network: regtest
  lnd_host: 127.0.0.1
  lnd_grpc_port: 10009
  tls_cert_path: ./bob-data/tls.cert
  macaroon_path: ./bob-data/data/chain/bitcoin/regtest/admin.macaroon
budget:
  daily_limit_msat: 100000000
  monthly_limit_msat: 3000000000
logging:
  level: info
  format: console
EOF
```

**Now edit it** and replace the `<PLACEHOLDER>` values:
```bash
nano kuberbolt-config/seller.yaml
```

**Key points:**
- `lnd_host: 127.0.0.1` — connects to YOUR local Bob LND
- `brain.url: http://127.0.0.1:8001` — the seller brain runs on THIS machine
- `tls_cert_path` and `macaroon_path` point to YOUR local `bob-data/`
- No credentials leave your machine

---

## Step 6: Build and Start the Financial Pod (Terminal 1)

```bash
cd agent-pod/financial-pod
go build -o financialpod ./cmd/financialpod
./financialpod --config ../../kuberbolt-config/seller.yaml
```

**Expected:**
```
INFO  connected to LND   alias=bob  synced=true
INFO  gRPC server listening  addr=0.0.0.0:6001
```

> **Keep this terminal open.**

---

## Step 7: Setup and Start the Seller Brain (Terminal 2)

```bash
cd ~/kuberbolt/agent-pod/brain
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create .env
cat > .env << EOF
SELLER_NOSTR_PRIVKEY=<SELLER_AGENT_PRIVKEY>
GOOGLE_API_KEY=<YOUR_GEMINI_API_KEY>
KUBERBOLT_RELAYS=wss://relay.damus.io,wss://nos.lol
BRAIN_HOST=0.0.0.0
BRAIN_PORT=8001
FP_GRPC_PORT=6001
EOF

python3 -m app.seller_agent
```

**Expected:**
```
============================================================
🚀 KUBERBOLT SELLER AGENT (Machine B)
============================================================
Local LAN IP: 192.168.1.11
Compute Server: http://0.0.0.0:8001
Financial Pod Target: 192.168.1.11:6001
============================================================
Listening for resolve_endpoint handshake requests...
```

> **Keep this terminal open.**

---

## Step 8: Verify Health

In a third terminal:

```bash
curl http://localhost:8001/health | python3 -m json.tool
```

```json
{
    "status": "ok",
    "role": "seller_brain",
    "local_ip": "192.168.1.11",
    "fp_grpc_port": 6001,
    "gemini_configured": true,
    "nostr_configured": true
}
```

---

## What Happens During the E2E Test

### Terminal 1 (Financial Pod):
```
⚡ [L402 CHALLENGE] Invoice created for Buyer -> Amount: 100 sats

╔══════════════════════════════════════════════════════════════════════╗
║ 🔒 HTLC LOCKED — BUYER PAYMENT RECEIVED & HELD                     ║
║  Status:       Funds secured in channel -> Executing AI Compute...  ║
╚══════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════╗
║ 💰 PAYMENT SETTLED — FUNDS CLAIMED VIA PREIMAGE                     ║
║  Status:       Invoice settled on Lightning -> Compute returned!    ║
╚══════════════════════════════════════════════════════════════════════╝
```

### Terminal 2 (Seller Brain):
```
INFO  Received resolve_endpoint request from buyer
INFO  Replying with endpoint: 192.168.1.11:6001
INFO  Received compute request for service_kind=text-summarization
INFO  Processing compute job (input length: 245 chars)...
INFO  Compute job completed successfully
```

---

## Troubleshooting

### "Bob LND won't sync"
- Verify Machine C's bitcoind is running and port 18443 is accessible
- Test: `nc -zv <MACHINE_C_IP> 18443`

### "Channel shows 0 remote balance"
- The channel must be funded by Alice (Machine A) and confirmed by Machine C mining blocks
- Verify: `docker exec bob lncli --network=regtest listchannels`

### "Gemini API errors"
- Verify key: `curl "https://generativelanguage.googleapis.com/v1beta/models?key=<YOUR_KEY>"`
- The brain falls back to local summarization if Gemini is down — the test will still work

### "No DM requests received"
- Machine A's buyer agent must be running
- Verify Nostr relays: `curl -o /dev/null -s -w '%{http_code}' https://relay.damus.io`

### "Buyer can't connect to seller FP on port 6001"
- Check macOS firewall: System Settings → Network → Firewall → Allow incoming connections
- Test from Machine A: `Test-NetConnection -ComputerName <MACHINE_B_IP> -Port 6001`

---

## Terminals Required: 2

| Terminal | Command | Must Stay Open? |
|----------|---------|-----------------|
| 1 | `./financialpod --config ...` | ✅ Yes |
| 2 | `python3 -m app.seller_agent` | ✅ Yes |
