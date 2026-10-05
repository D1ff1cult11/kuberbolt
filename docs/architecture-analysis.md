# Kuberbolt Architecture: Centralization vs Decentralization Analysis

## The Fundamental Question

Kuberbolt claims to be a **decentralized** compute marketplace. But where does centralization actually live in the current code, and does the multi-machine deployment match the architecture's intent?

---

## Component-by-Component Centralization Audit

### 1. SDK Server (FastAPI) — `api/main.py`

**Current role:** The SDK server is a **proxy** that sits between agents and Nostr relays.

```
Buyer Agent ──HTTP──▶ SDK Server ──WebSocket──▶ Nostr Relays
                          ▲
Seller Agent (brain) ─────┘ (registration only)
```

**What it does:**
- `POST /api/agents/register` → generates Nostr keypair, publishes kind:0 + kind:31990 to relays, stores session in Redis
- `GET /api/providers` → queries Nostr relays for kind:31990 service listings
- `POST /api/requests` → sends NIP-44 encrypted DMs via relays
- `POST /api/feedback` → publishes kind:7000 feedback events

**Is this centralized?** **YES — but intentionally as a convenience layer.**

The SDK server is NOT required by the protocol. It's a helper that does Nostr operations on behalf of agents who don't have their own Nostr client running. The seller brain (`seller_agent.py`) already connects to Nostr relays **directly** via `KuberboltAgent.from_existing_key()` for the NIP-44 endpoint listener.

**In a fully decentralized future:** Each agent would run its own Nostr client, and the SDK server would only exist as an optional registration gateway.

**For the hackathon:** The SDK server is fine. It doesn't see payment data, can't intercept L402 payments, and the NIP-44 DMs are end-to-end encrypted.

---

### 2. Bitcoin Core + LND — Where Should They Run?

This is the critical architectural decision. There are **3 valid deployment models**:

---

### Model A: All LND on One Machine (Current Guides)

```
┌────────────────────────────────────────────────┐
│  Machine C (Linux)                             │
│  ┌──────────┐  ┌─────────┐  ┌─────────┐      │
│  │ bitcoind │  │  Alice   │  │   Bob   │      │
│  │ (regtest)│  │  (LND)   │  │  (LND)  │      │
│  │  :18443  │  │  :10001  │  │  :10002 │      │
│  └──────────┘  └────┬─────┘  └────┬────┘      │
│       ▲             │             │            │
│       │        TLS+Macaroon  TLS+Macaroon      │
│       │             │             │            │
│  ┌────┴────┐        │             │            │
│  │  Redis  │        │             │            │
│  │  :6379  │        │             │            │
│  └─────────┘        │             │            │
│  ┌─────────┐        │             │            │
│  │ SDK API │        │             │            │
│  │  :8000  │        │             │            │
│  └─────────┘        │             │            │
└─────────────────────┼─────────────┼────────────┘
                      │ LAN         │ LAN
              ┌───────▼───┐   ┌─────▼──────┐
              │ Machine A │   │ Machine B  │
              │ (Windows) │   │  (macOS)   │
              │           │   │            │
              │ Buyer FP  │   │ Seller FP  │
              │  :6001    │   │  :6001     │
              │ Buyer     │   │ Seller     │
              │ Agent     │   │ Brain      │
              └───────────┘   └────────────┘
```

| Pros | Cons |
|------|------|
| One docker-compose starts everything | **TLS cert hostname mismatch** — certs only allow `localhost` and container names, not LAN IPs |
| Easy channel setup (same Docker network) | Admin macaroons must be copied to remote machines — security risk |
| Simple for demos | Not how real decentralized systems work |
| No Docker needed on A or B | Single point of failure for all Lightning |

**Verdict:** ❌ Broken without fixing `--tlsextraip` in docker-compose. Even with the fix, it's architecturally centralized.

---

### Model B: Each Machine Runs Its Own LND (True Decentralized)

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Machine C       │     │  Machine A       │     │  Machine B       │
│  (Linux)         │     │  (Windows)       │     │  (macOS)         │
│                  │     │                  │     │                  │
│  ┌──────────┐   │     │  ┌──────────┐   │     │  ┌──────────┐   │
│  │ bitcoind │   │     │  │  Alice   │   │     │  │   Bob    │   │
│  │ (regtest)│   │     │  │  (LND)   │   │     │  │  (LND)   │   │
│  │  :18443  │◀──┼─────┼──│ :10009   │   │     │  │  :10009  │──┼─┐
│  └──────────┘   │     │  └────┬─────┘   │     │  └────┬─────┘  │ │
│                  │     │       │local    │     │       │local   │ │
│  ┌─────────┐   │     │  ┌────▼─────┐   │     │  ┌────▼─────┐  │ │
│  │  Redis  │   │     │  │ Buyer FP │   │     │  │Seller FP │  │ │
│  │  :6379  │   │     │  │  :6001   │   │     │  │  :6001   │  │ │
│  └─────────┘   │     │  └──────────┘   │     │  └──────────┘  │ │
│  ┌─────────┐   │     │  ┌──────────┐   │     │  ┌──────────┐  │ │
│  │ SDK API │   │     │  │  Buyer   │   │     │  │ Seller   │  │ │
│  │  :8000  │   │     │  │  Agent   │   │     │  │  Brain   │  │ │
│  └─────────┘   │     │  └──────────┘   │     │  └──────────┘  │ │
└──────────────────┘     └──────────────────┘     └──────────────────┘
         ▲                                                          │
         └──────────────────bitcoind RPC────────────────────────────┘
                    Alice ◀──Lightning Channel──▶ Bob
```

| Pros | Cons |
|------|------|
| **No TLS issue** — LND is on localhost, cert matches | Docker needed on all 3 machines |
| **Macaroons stay local** — no secrets leave the machine | Channel setup requires cross-machine LND commands |
| **Truly decentralized** — matches the real architecture | Each LND needs to connect to bitcoind over LAN |
| Each agent controls its own wallet | Slightly more complex setup |

**Verdict:** ✅ This is architecturally correct and avoids the TLS blocker entirely.

---

### Model C: Single Machine (Hackathon Demo)

```
┌────────────────────────────────────────────────────────────────┐
│  Machine C (Linux) — Everything                                │
│                                                                │
│  Docker: bitcoind + alice + bob + redis                         │
│                                                                │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │ Buyer FP    │  │ Seller FP    │  │ SDK Server          │  │
│  │ :6002       │  │ :6001        │  │ :8000               │  │
│  │ ↕ Alice     │  │ ↕ Bob        │  │ Frontend :5173      │  │
│  │  :10001     │  │  :10002      │  └─────────────────────┘  │
│  └──────┬──────┘  └──────┬───────┘                            │
│         │    gRPC L402    │                                    │
│         └────────────────┘                                    │
│  ┌─────────────┐  ┌──────────────┐                            │
│  │ Buyer Agent │  │ Seller Brain │                            │
│  │ (LangChain) │  │ :8001        │                            │
│  └─────────────┘  └──────────────┘                            │
└────────────────────────────────────────────────────────────────┘
```

| Pros | Cons |
|------|------|
| **Zero networking issues** — everything is localhost | Doesn't prove multi-machine capability |
| **5 minutes to set up** | All eggs in one basket |
| Perfect for hackathon demo recording | |

**Verdict:** ✅ Best for validating the full flow works before attempting multi-machine.

---

## Recommended Approach: Model B (Decentralized)

### How It Works Step by Step

#### Step 1: Machine C starts Bitcoin Core

Machine C runs bitcoind in Docker with ports exposed to LAN:

```bash
# Machine C
docker run -d --name bitcoind \
  -p 18443:18443 -p 28332:28332 -p 28333:28333 \
  lncm/bitcoind:v24.0 \
  -regtest=1 -rpcallowip=0.0.0.0/0 -rpcbind=0.0.0.0 \
  -rpcuser=devuser -rpcpassword=devpass \
  -fallbackfee=0.0002 -txindex=1 \
  -zmqpubrawblock=tcp://0.0.0.0:28332 \
  -zmqpubrawtx=tcp://0.0.0.0:28333
```

#### Step 2: Machine A starts Alice LND (connects to Machine C's bitcoind)

```bash
# Machine A (Windows) — run in PowerShell
docker run -d --name alice `
  -p 10009:10009 -p 8080:8080 -p 9735:9735 `
  -v ${PWD}/alice-data:/root/.lnd `
  lightninglabs/lnd:v0.17.4-beta `
  --noseedbackup `
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

**Why this solves the TLS problem:** Alice's LND runs locally. The Financial Pod connects to `localhost:10009`. The TLS cert includes `localhost` by default. No hostname mismatch.

**Why macaroons stay safe:** The `alice-data` volume stays on Machine A. No files leave this machine.

#### Step 3: Machine B starts Bob LND (connects to Machine C's bitcoind)

```bash
# Machine B (macOS)
docker run -d --name bob \
  -p 10009:10009 -p 8080:8080 -p 9735:9735 \
  -v $(pwd)/bob-data:/root/.lnd \
  lightninglabs/lnd:v0.17.4-beta \
  --noseedbackup \
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

#### Step 4: Fund Alice and Open Channel

```bash
# On Machine C — mine coins to Alice's address
# First get Alice's address (run on Machine A)
docker exec alice lncli --network=regtest newaddress p2wkh

# Then mine to that address (run on Machine C)
docker exec bitcoind bitcoin-cli -regtest -rpcuser=devuser -rpcpassword=devpass \
  generatetoaddress 101 <ALICE_ADDRESS>

# On Machine A — get Bob's pubkey and connect
# First get Bob's pubkey (run on Machine B)
docker exec bob lncli --network=regtest getinfo  # → identity_pubkey

# Connect Alice to Bob (run on Machine A)
docker exec alice lncli --network=regtest connect <BOB_PUBKEY>@<MACHINE_B_IP>:9735

# Open channel (run on Machine A)
docker exec alice lncli --network=regtest openchannel \
  --node_key=<BOB_PUBKEY> --local_amt=500000

# Mine 6 blocks to confirm (run on Machine C)
docker exec bitcoind bitcoin-cli -regtest -rpcuser=devuser -rpcpassword=devpass \
  generatetoaddress 6 <ALICE_ADDRESS>
```

#### Step 5: Start Financial Pods

**Machine A — Buyer FP config (`buyer.yaml`):**
```yaml
lightning:
  network: regtest
  lnd_host: 127.0.0.1        # ← LOCAL, not Machine C
  lnd_grpc_port: 10009        # ← default LND port
  tls_cert_path: ./alice-data/tls.cert         # ← LOCAL file
  macaroon_path: ./alice-data/data/chain/bitcoin/regtest/admin.macaroon  # ← LOCAL
```

**Machine B — Seller FP config (`seller.yaml`):**
```yaml
lightning:
  network: regtest
  lnd_host: 127.0.0.1        # ← LOCAL, not Machine C
  lnd_grpc_port: 10009        # ← default LND port
  tls_cert_path: ./bob-data/tls.cert           # ← LOCAL file
  macaroon_path: ./bob-data/data/chain/bitcoin/regtest/admin.macaroon    # ← LOCAL
```

---

## What Is Centralized vs Decentralized (Honest Assessment)

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  DECENTRALIZED (no single point of failure)                     │
│  ═══════════════════════════════════════                        │
│  ✅ Lightning Payments — Alice pays Bob directly, no middleman  │
│  ✅ L402 Protocol — Buyer FP ↔ Seller FP, direct gRPC          │
│  ✅ NIP-44 DMs — end-to-end encrypted, relays can't read them  │
│  ✅ Nostr Discovery — kind:31990 on public relays               │
│  ✅ Compute — runs on seller's machine, buyer never sees it     │
│  ✅ LND Nodes — each agent has its own wallet (Model B)         │
│                                                                 │
│  CENTRALIZED (required, but by design)                          │
│  ═════════════════════════════════════                          │
│  ⚠️  SDK Server — proxy for Nostr operations (convenience)      │
│  ⚠️  Redis — session store for agent auth tokens                │
│  ⚠️  Bitcoin Core — single regtest node (unavoidable on regtest)│
│                                                                 │
│  CENTRALIZED (should be fixed)                                  │
│  ══════════════════════════════                                 │
│  ❌ LND on one machine (Model A) — defeats the purpose          │
│  ❌ Admin macaroons leaving machines — security violation        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### The SDK Server Is NOT a Centralization Problem

The SDK server is an **optional convenience layer**. Here's proof:

1. The seller brain already connects to Nostr relays **directly** via `KuberboltAgent.from_existing_key()` — it does NOT go through the SDK server for NIP-44 listening.

2. The L402 payment flow (the money part) goes **directly** between Financial Pods over gRPC — the SDK server is completely uninvolved.

3. If the SDK server goes down mid-transaction, the L402 payment still settles — it's already locked in the Lightning channel.

The SDK server only matters for:
- Initial agent registration (one-time)
- Discovery queries (could be done directly by agent)
- Sending the initial DM to the seller (could be done directly)

---

## Latency Analysis for Model B

```
Hop   What                              Protocol       Est. Latency
────  ────                              ────────       ────────────
1     Buyer Agent → SDK Server          HTTP (LAN)     3-5 ms
2     SDK → Nostr Relay (discover)      WebSocket      200-500 ms
3     Nostr → SDK (results)             WebSocket      200-500 ms
4     SDK → Buyer Agent (providers)     HTTP (LAN)     3-5 ms
5     Buyer Agent → SDK (send DM)       HTTP (LAN)     3-5 ms
6     SDK → Nostr Relay (NIP-44 DM)     WebSocket      300-800 ms
7     Nostr → Seller Brain (DM poll)    WebSocket      0-3000 ms *
8     Seller → Nostr (reply)            WebSocket      300-800 ms
9     Nostr → SDK (reply)               WebSocket      300-800 ms
10    SDK → Buyer Agent (endpoint)      HTTP (LAN)     3-5 ms
─── subtotal: discovery + handshake ─── ─────────────  ~2-6 seconds

11    Buyer FP → Seller FP (unauth)     gRPC (LAN)     3-10 ms
12    Seller FP → Buyer FP (402)        gRPC (LAN)     3-10 ms
13    Buyer LND → Seller LND (HTLC)     Lightning      50-200 ms
14    Buyer FP → Seller FP (auth)       gRPC (LAN)     3-10 ms
15    Seller FP → Brain (/compute)      HTTP (local)   2000-5000 ms **
16    Seller FP settle (preimage)        LND local      10-50 ms
17    Seller FP → Buyer FP (result)     gRPC (LAN)     3-10 ms
─── subtotal: L402 payment + compute ── ─────────────  ~2.5-6 seconds

18    Buyer Agent → SDK (feedback)      HTTP (LAN)     3-5 ms
19    SDK → Nostr (kind:7000)           WebSocket      300-800 ms
─── subtotal: feedback ──────────────── ─────────────  ~0.5 seconds

═══ TOTAL E2E ══════════════════════════════════════   ~5-13 seconds
```

\* Seller brain polls every 3 seconds, so worst case adds 3s.
\** Gemini API call dominates compute time.

**The bottlenecks are:**
1. Nostr relay round-trips (~1-2s per hop)
2. Gemini API call (~2-5s)
3. Seller's poll interval (up to 3s wasted waiting)

**The L402 payment itself is extremely fast** — under 300ms on a LAN. The cryptographic handshake (HODL invoice → HTLC lock → compute → settle) is well-designed.

---

## Security Model

### What's Protected

| Secret | Where It Lives | Who Can Access |
|--------|---------------|---------------|
| Alice's LND wallet | Machine A `alice-data/` | Only Machine A |
| Bob's LND wallet | Machine B `bob-data/` | Only Machine B |
| Agent Nostr private keys | Machine C Redis (Fernet-encrypted) | SDK server process only |
| Buyer session token | Machine A env vars | Buyer agent process only |
| NIP-44 DM content | Nostr relays (encrypted) | Only sender + recipient |
| L402 preimage | Seller FP memory | Only seller until settlement |
| Gemini API key | Machine B `.env` | Seller brain process only |

### What Could Go Wrong

| Threat | Impact | Mitigation |
|--------|--------|------------|
| Machine C compromised | bitcoind access, can mine blocks (regtest only) | Use testnet/mainnet for production |
| Redis breached | Encrypted private keys exposed | Fernet key rotation, network isolation |
| Nostr relay malicious | Can drop/delay messages | Use multiple relays (already configured) |
| Buyer FP compromised | Can drain Alice's LND balance | Use baked macaroons with limited permissions |
| LAN sniffing | gRPC between FPs is plaintext | Add mTLS between pods (Phase 5 per code comments) |
