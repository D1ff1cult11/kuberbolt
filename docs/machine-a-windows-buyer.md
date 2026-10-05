# Machine A — Buyer Agent Setup Guide (Windows)

## Your Role

You are the **buyer agent operator**. Your machine runs:
- **Alice LND Node** (Docker) — your own Lightning wallet, connected to Machine C's bitcoind
- **Go Financial Pod** — handles L402 payments via gRPC
- **LangChain Buyer Agent** — discovers sellers, negotiates, pays, gets results

**Your LND credentials never leave this machine.**

---

## What You Need From Machine C

| Item | What It Is |
|------|-----------|
| **Machine C IP** | LAN IP of the Linux machine (e.g. `192.168.1.12`) |
| **Machine B IP** | LAN IP of the macOS machine (e.g. `192.168.1.11`) |
| **Buyer `agent_pubkey`** | From registration response |
| **Buyer `agent_privkey`** | From registration response |
| **Buyer `session_token`** | From registration response |

---

## Prerequisites

| Requirement | Check Command |
|-------------|---------------|
| Python 3.11+ | `python --version` |
| Go 1.21+ | `go version` |
| Docker Desktop | `docker --version` |
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

## Step 2: Get Your LAN IP

```powershell
(Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias Wi-Fi).IPAddress
```

Write this down as `<MACHINE_A_IP>`. Share it with Machine B (for Lightning channel).

---

## Step 3: Start Alice LND (Docker)

Alice connects to Machine C's bitcoind over the LAN. Replace `<MACHINE_C_IP>`.

```powershell
docker run -d --name alice `
  -p 10009:10009 -p 8080:8080 -p 9735:9735 `
  -v ${PWD}/alice-data:/root/.lnd `
  lightninglabs/lnd:v0.17.4-beta `
  --noseedbackup `
  --trickledelay=5000 `
  --alias=alice `
  --bitcoin.active `
  --bitcoin.regtest `
  --bitcoin.node=bitcoind `
  --bitcoind.rpchost=<MACHINE_C_IP>:18443 `
  --bitcoind.rpcuser=devuser `
  --bitcoind.rpcpass=devpass `
  --bitcoind.zmqpubrawblock=tcp://<MACHINE_C_IP>:28332 `
  --bitcoind.zmqpubrawtx=tcp://<MACHINE_C_IP>:28333 `
  --rpclisten=0.0.0.0:10009 `
  --restlisten=0.0.0.0:8080 `
  --listen=0.0.0.0:9735 `
  --tlsextradomain=localhost
```

Wait 10 seconds, then verify:

```powershell
docker exec alice lncli --network=regtest getinfo
```

You should see `"synced_to_chain": true` and `"identity_pubkey": "02abc..."`.

**Write down:**
- **Alice's LND pubkey** (`identity_pubkey`) — share with Machine C
- **Alice's wallet address:**

```powershell
docker exec alice lncli --network=regtest newaddress p2wkh
```

Share this address with Machine C so they can mine coins to you.

---

## Step 4: Wait for Funding

Tell Machine C to mine 101 blocks to your Alice address. Then verify:

```powershell
docker exec alice lncli --network=regtest walletbalance
# Should show non-zero confirmed_balance
```

---

## Step 5: Open Lightning Channel to Bob

Get Bob's LND pubkey and Machine B's IP from your teammates.

```powershell
# Connect to Bob
docker exec alice lncli --network=regtest connect <BOB_LND_PUBKEY>@<MACHINE_B_IP>:9735

# Open channel (500,000 sats)
docker exec alice lncli --network=regtest openchannel `
  --node_key=<BOB_LND_PUBKEY> `
  --local_amt=500000
```

Tell Machine C to mine 6 blocks to confirm the channel, then verify:

```powershell
docker exec alice lncli --network=regtest listchannels
# Look for "active": true
```

---

## Step 6: Create Buyer Financial Pod Config

Create `kuberbolt-config\buyer.yaml`:

```yaml
agent:
  name: buyer
  role: client
  nostr_npub: "<BUYER_AGENT_PUBKEY>"
  nostr_priv_key: "<BUYER_AGENT_PRIVKEY>"
  created_at: "2026-10-05T00:00:00Z"
services: []
network:
  grpc_port: 6001
  public_host: 0.0.0.0
  nostr_relays:
    - wss://relay.damus.io
    - wss://nos.lol
brain:
  url: http://127.0.0.1:9999
lightning:
  network: regtest
  lnd_host: 127.0.0.1
  lnd_grpc_port: 10009
  tls_cert_path: ./alice-data/tls.cert
  macaroon_path: ./alice-data/data/chain/bitcoin/regtest/admin.macaroon
budget:
  daily_limit_msat: 100000000
  monthly_limit_msat: 3000000000
logging:
  level: info
  format: console
```

**Key points:**
- `lnd_host: 127.0.0.1` — connects to YOUR local Alice LND (no remote connection)
- `lnd_grpc_port: 10009` — standard LND gRPC port
- `tls_cert_path` and `macaroon_path` point to YOUR local `alice-data/` directory
- No credentials leave your machine

---

## Step 7: Build and Start the Financial Pod

```powershell
cd agent-pod\financial-pod
go build -o financialpod.exe .\cmd\financialpod
.\financialpod.exe --config ..\..\kuberbolt-config\buyer.yaml
```

**Expected:**
```
INFO  connected to LND   alias=alice  synced=true
INFO  gRPC server listening  addr=0.0.0.0:6001
```

> **Keep this terminal open.**

---

## Step 8: Setup Buyer Agent (New Terminal)

```powershell
cd kuberbolt\agent-pod\brain
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Step 9: Set Environment Variables and Run

```powershell
$env:SDK_SERVER_URL = "http://<MACHINE_C_IP>:8000"
$env:BUYER_NOSTR_PUBKEY = "<BUYER_AGENT_PUBKEY>"
$env:BUYER_SESSION_TOKEN = "<BUYER_SESSION_TOKEN>"
$env:BUYER_FP_ADDR = "127.0.0.1:6001"
$env:GOOGLE_API_KEY = "<YOUR_GEMINI_API_KEY>"

python -m app.buyer_agent "Find a text summarization provider on the Kuberbolt network and use it to summarize this text: 'The Lightning Network is a payment channel network built on top of Bitcoin. It enables instant, low-fee transactions by routing payments through bidirectional payment channels secured by Hash Time-Locked Contracts.'"
```

---

## What You Should See

```
Running agent with prompt: Find a text summarization provider...

Thought: I need to find providers
Action: discover_providers("text-summarization")
Observation: [{"service_name": "Text Summarization", ...}]

Action: request_endpoint("<seller_pubkey>")
Observation: {"host": "192.168.1.11", "port": 6001}

Action: call_service("192.168.1.11", 6001, "The Lightning Network...")
Observation: {"summary": "..."}

Action: publish_feedback(...)
Final Answer: Successfully summarized the text!
```

---

## Troubleshooting

### "Alice LND won't sync"
- Check Machine C's bitcoind is running and port 18443 is accessible
- Test: `Test-NetConnection -ComputerName <MACHINE_C_IP> -Port 18443`

### "Channel not active"
- Ask Machine C to mine 6 more blocks
- Verify: `docker exec alice lncli --network=regtest listchannels`

### "grpcurl not found"
- Install grpcurl: `go install github.com/fullstorydev/grpcurl/cmd/grpcurl@latest`
- Or use Chocolatey: `choco install grpcurl`

### "Connection refused to seller FP"
- Check Machine B's firewall allows port 6001
- Test: `Test-NetConnection -ComputerName <MACHINE_B_IP> -Port 6001`
