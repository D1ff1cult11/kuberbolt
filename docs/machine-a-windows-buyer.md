# Machine A — Buyer Agent Setup Guide (Windows)

## Your Role

You are the **buyer agent operator**. Your machine runs:
- **Go Financial Pod** — handles L402 payments via gRPC, connected to Alice's LND node on Machine C
- **LangChain Buyer Agent** — autonomous AI agent that discovers sellers, negotiates endpoints, pays for compute, and publishes feedback

---

## What You Need From Machine C (Linux)

Before starting, get these from your teammate running Machine C:

| Item | What It Is | Example |
|------|-----------|---------|
| **Machine C IP** | LAN IP of the Linux machine | `192.168.1.12` |
| **Alice TLS cert** | File: `tls.cert` | Copy to `kuberbolt-config\tls.cert` |
| **Alice admin macaroon** | File: `admin.macaroon` | Copy to `kuberbolt-config\admin.macaroon` |
| **Alice LND pubkey** | 66-char hex string | `02abc123...` |
| **Buyer agent_pubkey** | From registration | `npub1xyz...` or hex |
| **Buyer agent_privkey** | From registration | `hex string` |
| **Buyer session_token** | From registration | `token string` |

---

## Prerequisites

| Requirement | Check Command |
|-------------|---------------|
| Python 3.11+ | `python --version` |
| Go 1.21+ | `go version` |
| Git | `git --version` |

---

## Step 1: Clone the Repository

```powershell
git clone https://github.com/devlup-labs/kuberbolt.git
cd kuberbolt
git checkout dev
git pull origin dev
```

---

## Step 2: Place LND Credentials

Create the config directory and copy the files you received from Machine C:

```powershell
mkdir kuberbolt-config -Force
```

Copy `tls.cert` and `admin.macaroon` (received from Machine C) into `kuberbolt-config\`.

Verify they exist:
```powershell
dir kuberbolt-config\
```

Expected:
```
    Directory: D:\...\kuberbolt\kuberbolt-config

Mode                 LastWriteTime         Length Name
----                 -------------         ------ ----
-a---          10/04/2026  5:30 PM            836 tls.cert
-a---          10/04/2026  5:30 PM            293 admin.macaroon
```

---

## Step 3: Create Buyer Financial Pod Config

Create `kuberbolt-config\buyer.yaml` with the following content.

**Replace all `<PLACEHOLDER>` values with real values from Machine C.**

```yaml
agent:
  name: buyer
  role: client
  nostr_npub: "<BUYER_AGENT_PUBKEY>"
  nostr_priv_key: "<BUYER_AGENT_PRIVKEY>"
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
  tls_cert_path: <FULL_PATH_TO>\kuberbolt-config\tls.cert
  macaroon_path: <FULL_PATH_TO>\kuberbolt-config\admin.macaroon
budget:
  daily_limit_msat: 100000000
  monthly_limit_msat: 3000000000
logging:
  level: info
  format: console
```

**Important notes:**
- `lnd_host` = Machine C's LAN IP (where Docker LND runs)
- `lnd_grpc_port` = `10001` (Alice's mapped port on Machine C)
- `tls_cert_path` and `macaroon_path` must be **full absolute paths** using forward slashes  
  Example: `D:/Dev Projects/kuberbolt/kuberbolt-config/tls.cert`

---

## Step 4: Build the Go Financial Pod

```powershell
cd agent-pod\financial-pod
go build -o financialpod.exe .\cmd\financialpod
```

If the build succeeds, you'll see `financialpod.exe` in the current directory.

---

## Step 5: Start the Financial Pod

```powershell
.\financialpod.exe --config ..\..\kuberbolt-config\buyer.yaml
```

**Expected output:**
```
INFO  gateway: connected to LND   alias=alice  pubkey=02abc123...  synced=true
INFO  gRPC server listening        addr=0.0.0.0:6001
```

If you see `connected to LND` with `synced=true`, the Financial Pod is successfully connected to Alice's Lightning node on Machine C.

> **Keep this terminal open.** The Financial Pod must stay running.

---

## Step 6: Setup the Buyer Agent (New Terminal)

Open a **new PowerShell terminal**:

```powershell
cd kuberbolt\agent-pod\brain
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Step 7: Set Environment Variables

```powershell
$env:SDK_SERVER_URL = "http://<MACHINE_C_IP>:8000"
$env:BUYER_NOSTR_PUBKEY = "<BUYER_AGENT_PUBKEY>"
$env:BUYER_SESSION_TOKEN = "<BUYER_SESSION_TOKEN>"
$env:BUYER_FP_ADDR = "127.0.0.1:6001"
$env:GOOGLE_API_KEY = "<YOUR_GEMINI_API_KEY>"
```

Replace all `<PLACEHOLDER>` values with the real values from Machine C.

---

## Step 8: Run the Buyer Agent

```powershell
python -m app.buyer_agent "Find a text summarization provider on the Kuberbolt network and use it to summarize this text: 'The Lightning Network is a payment channel network built on top of Bitcoin. It enables instant, low-fee transactions by routing payments through bidirectional payment channels secured by Hash Time-Locked Contracts. Payments achieve sub-second finality with near-zero fees, only touching the base blockchain when channels open or settle.'"
```

---

## What You Should See

### In the Buyer Agent terminal:

```
Running agent with prompt: Find a text summarization provider...

Thought: I need to discover providers that offer text summarization
Action: discover_providers
Action Input: text-summarization
Observation: [{"service_name": "Text Summarization", "agent_pubkey": "npub1..."}]

Thought: I found a provider. Now I need to get their endpoint
Action: request_endpoint
Action Input: <seller_pubkey>
Observation: {"host": "192.168.1.11", "port": 6001}

Thought: I have the endpoint. Now I'll call the service
Action: call_service
Action Input: {"host": "192.168.1.11", "port": 6001, "text_to_summarize": "The Lightning Network..."}
Observation: {"summary": "The Lightning Network is Bitcoin's layer-2 solution..."}

Thought: I got the result. Let me publish feedback
Action: publish_feedback
Action Input: {"provider_pubkey": "...", "rating": 5, "feedback": "Excellent summarization"}

Final Answer: The text has been summarized: "The Lightning Network is Bitcoin's layer-2 solution..."
```

### In the Financial Pod terminal:

```
INFO  gRPC RPC completed  method=/kuberbolt.v1.FinancialPodService/CallService
INFO  received L402 challenge  payment_hash=abc123...  amount_msat=100000
INFO  paying HODL invoice in background  payment_hash=abc123...
INFO  CallProvider completed successfully  job_id=...  amount_msat=100000
```

---

## Troubleshooting

### "LND connection failed"
- Check Machine C's IP is correct in `buyer.yaml`
- Verify Alice's LND is running: ask Machine C to run `docker exec alice lncli --network=regtest getinfo`
- Check Windows Firewall isn't blocking outbound connections to port 10001
- Verify `tls.cert` and `admin.macaroon` are the correct files from Alice (not Bob)

### "go build" fails
- Ensure Go 1.21+ is installed: `go version`
- If module errors: `go mod tidy` then retry

### "SDK_SERVER_URL connection refused"
- Verify Machine C's SDK server is running on port 8000
- Test: `curl http://<MACHINE_C_IP>:8000/health`
- Check if Machine C's firewall allows incoming on port 8000

### "insufficient balance" or "no route"
- Ask Machine C to mine more blocks and verify the channel has balance
- The channel needs to be active with sufficient local balance on Alice's side

### "SELLER_NOSTR_PRIVKEY not set" / "NIP-44 DM not received"
- This error is on the **seller side** (Machine B) — tell your teammate to check their setup
- Increase timeout: `$env:KUBERBOLT_HANDSHAKE_TIMEOUT_SECONDS = "60"`

---

## Quick Reference

| Service | Address | Port |
|---------|---------|------|
| Buyer Financial Pod | `127.0.0.1` | `6001` |
| Alice LND (on Machine C) | `<MACHINE_C_IP>` | `10001` |
| SDK Server (on Machine C) | `<MACHINE_C_IP>` | `8000` |
| Frontend (on Machine C) | `<MACHINE_C_IP>` | `5173` |
