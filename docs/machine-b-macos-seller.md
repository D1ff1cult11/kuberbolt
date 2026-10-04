# Machine B — Seller Agent Setup Guide (macOS)

## Your Role

You are the **seller agent operator**. Your machine runs:
- **Go Financial Pod** — issues L402 challenges, holds HODL invoices, settles payments after compute
- **Seller Brain** — FastAPI compute server (Gemini AI summarization) + NIP-44 endpoint resolver (listens for buyer DMs and replies with your IP:port)

---

## What You Need From Machine C (Linux)

Before starting, get these from your teammate running Machine C:

| Item | What It Is | Example |
|------|-----------|---------|
| **Machine C IP** | LAN IP of the Linux machine | `192.168.1.12` |
| **Bob TLS cert** | File: `tls.cert` | Copy to `kuberbolt-config/tls.cert` |
| **Bob admin macaroon** | File: `admin.macaroon` | Copy to `kuberbolt-config/admin.macaroon` |
| **Bob LND pubkey** | 66-char hex string | `03def456...` |
| **Seller agent_pubkey** | From registration | `npub1abc...` or hex |
| **Seller agent_privkey** | From registration | `hex string` |
| **Seller session_token** | From registration | `token string` |

You also need:
- **Google API Key** — for Gemini AI (get from https://aistudio.google.com/apikey)

---

## Prerequisites

| Requirement | Check Command |
|-------------|---------------|
| Python 3.11+ | `python3 --version` |
| Go 1.21+ | `go version` |
| Git | `git --version` |

Install Go if needed:
```bash
brew install go
```

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/devlup-labs/kuberbolt.git
cd kuberbolt
git checkout dev
git pull origin dev
```

---

## Step 2: Place LND Credentials

Copy the `bob/tls.cert` and `bob/admin.macaroon` files you received from Machine C:

```bash
mkdir -p kuberbolt-config
cp /path/to/received/tls.cert kuberbolt-config/tls.cert
cp /path/to/received/admin.macaroon kuberbolt-config/admin.macaroon
```

If they were sent via AirDrop, they'll be in `~/Downloads/`:
```bash
cp ~/Downloads/tls.cert kuberbolt-config/tls.cert
cp ~/Downloads/admin.macaroon kuberbolt-config/admin.macaroon
```

Verify:
```bash
ls -la kuberbolt-config/
# Should show tls.cert and admin.macaroon
```

---

## Step 3: Create Seller Financial Pod Config

Create `kuberbolt-config/seller.yaml`:

```bash
cat > kuberbolt-config/seller.yaml << 'YAMLEOF'
agent:
  name: seller
  role: provider
  nostr_npub: "<SELLER_AGENT_PUBKEY>"
  nostr_priv_key: "<SELLER_AGENT_PRIVKEY>"
  created_at: "2026-10-04T00:00:00Z"
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
  tls_cert_path: <FULL_PATH>/kuberbolt-config/tls.cert
  macaroon_path: <FULL_PATH>/kuberbolt-config/admin.macaroon
budget:
  daily_limit_msat: 100000000
  monthly_limit_msat: 3000000000
logging:
  level: info
  format: console
YAMLEOF
```

**Now edit it** and replace all `<PLACEHOLDER>` values:

```bash
nano kuberbolt-config/seller.yaml
```

**Important notes:**
- `lnd_host` = Machine C's LAN IP (where Docker LND runs)
- `lnd_grpc_port` = `10002` (Bob's mapped port on Machine C)
- `brain.url` = `http://127.0.0.1:8001` (the seller brain runs locally on THIS machine)
- `tls_cert_path` and `macaroon_path` must be full absolute paths  
  Example: `/Users/yourname/kuberbolt/kuberbolt-config/tls.cert`
- `price_msat: 100000` = 100 sats per request (in millisatoshis)

---

## Step 4: Build the Go Financial Pod

```bash
cd agent-pod/financial-pod
go build -o financialpod ./cmd/financialpod
```

Verify:
```bash
ls -la financialpod
# Should show the compiled binary
```

---

## Step 5: Start the Financial Pod (Terminal 1)

```bash
./financialpod --config ../../kuberbolt-config/seller.yaml
```

**Expected output:**
```
INFO  gateway: connected to LND   alias=bob  pubkey=03def456...  synced=true
INFO  gRPC server listening        addr=0.0.0.0:6001
```

If you see `connected to LND` with `synced=true`, the Financial Pod is successfully connected to Bob's Lightning node on Machine C.

> **Keep this terminal open.** The Financial Pod must stay running.

---

## Step 6: Setup the Seller Brain (Terminal 2)

Open a **new terminal**:

```bash
cd ~/kuberbolt/agent-pod/brain
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Step 7: Create Brain `.env` File

```bash
cat > .env << EOF
SELLER_NOSTR_PRIVKEY=<SELLER_AGENT_PRIVKEY_FROM_REGISTRATION>
GOOGLE_API_KEY=<YOUR_GEMINI_API_KEY>
KUBERBOLT_RELAYS=wss://relay.damus.io,wss://nos.lol
BRAIN_HOST=0.0.0.0
BRAIN_PORT=8001
FP_GRPC_PORT=6001
EOF
```

**Replace the placeholders** with real values.

---

## Step 8: Start the Seller Brain

```bash
python3 -m app.seller_agent
```

**Expected output:**
```
============================================================
🚀 KUBERBOLT SELLER AGENT (Machine B)
============================================================
Local LAN IP: 192.168.1.11
Compute Server: http://0.0.0.0:8001
Financial Pod Target: 192.168.1.11:6001
============================================================

INFO  Starting Seller NIP-44 Endpoint Resolver...
  - Local LAN IP: 192.168.1.11
  - FP gRPC Port: 6001
  - Relays: ['wss://relay.damus.io', 'wss://nos.lol']

INFO  Seller agent connected to Nostr relays. Pubkey: abc123...
INFO  Listening for resolve_endpoint handshake requests from buyer agents...
```

> **Keep this terminal open.** The brain must stay running.

---

## Step 9: Verify Health

In a **third terminal**:

```bash
curl http://localhost:8001/health | python3 -m json.tool
```

Expected:
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

All fields should be `true`. If `gemini_configured` is `false`, check your `GOOGLE_API_KEY`.

---

## What Happens During the E2E Test

When Machine A (Buyer) runs their agent, you'll see this sequence in your terminals:

### Financial Pod Terminal:
```
⚡ [L402 CHALLENGE] Invoice created for Buyer -> Amount: 100 sats (100000 mSat) | Hash: abc123...

╔══════════════════════════════════════════════════════════════════════╗
║ 🔒 HTLC LOCKED — BUYER PAYMENT RECEIVED & HELD                     ║
║  Amount:       100 sats (100000 mSat)                               ║
║  Payment Hash: abc123def456...                                      ║
║  Status:       Funds secured in channel -> Executing AI Compute...  ║
╚══════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════╗
║ 💰 PAYMENT SETTLED — FUNDS CLAIMED VIA PREIMAGE                     ║
║  Amount:       100 sats (100000 mSat)                               ║
║  Payment Hash: abc123def456...                                      ║
║  Status:       Invoice settled on Lightning -> Compute returned!    ║
╚══════════════════════════════════════════════════════════════════════╝
```

### Seller Brain Terminal:
```
INFO  Received resolve_endpoint request from buyer
INFO  Replying with endpoint: 192.168.1.11:6001

INFO  Received compute request for service_kind=text-summarization
INFO  Processing compute job (input length: 245 chars)...
INFO  Compute job completed successfully for service_kind=text-summarization
```

---

## Troubleshooting

### "LND connection failed"
- Verify Machine C's IP is correct in `seller.yaml`
- Verify Bob's LND is running: ask Machine C to run `docker exec bob lncli --network=regtest getinfo`
- Check that port 10002 on Machine C is reachable: `nc -zv <MACHINE_C_IP> 10002`
- Make sure you're using Bob's creds (not Alice's)

### "SELLER_NOSTR_PRIVKEY is not set"
- Check `agent-pod/brain/.env` has the correct key
- Or export it: `export SELLER_NOSTR_PRIVKEY=<hex_key>`

### "Gemini API returned status 400/403"
- Verify your `GOOGLE_API_KEY` is valid
- Test it: `curl "https://generativelanguage.googleapis.com/v1beta/models?key=<KEY>"`
- The brain has a local fallback summarizer, so the test will still work without Gemini

### "No resolve_endpoint requests received"
- The buyer agent on Machine A must be running for DMs to arrive
- Verify Nostr relays are reachable: `curl -o /dev/null -s -w '%{http_code}' https://relay.damus.io`
- Both agents must use the same relay list

### Financial Pod crashes on start
- Double-check all paths in `seller.yaml` are absolute paths
- Verify `tls.cert` and `admin.macaroon` are readable: `cat kuberbolt-config/tls.cert`

---

## Quick Reference

| Service | Address | Port |
|---------|---------|------|
| Seller Financial Pod | `0.0.0.0` | `6001` |
| Seller Brain (Compute) | `0.0.0.0` | `8001` |
| Bob LND (on Machine C) | `<MACHINE_C_IP>` | `10002` |
| SDK Server (on Machine C) | `<MACHINE_C_IP>` | `8000` |

### Terminals Required: 2 (minimum)

| Terminal | What Runs | Must Stay Open? |
|----------|-----------|-----------------|
| Terminal 1 | `./financialpod --config ...` | ✅ Yes |
| Terminal 2 | `python3 -m app.seller_agent` | ✅ Yes |
| Terminal 3 | Health checks / debugging | Optional |
