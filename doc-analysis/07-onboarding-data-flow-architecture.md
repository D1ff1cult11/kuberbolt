# Onboarding Data Flow Architecture — Frontend, SDK, FP, and Nostr

## The Core Decision: Who Gets What Data

There are two completely separate categories of information an agent provides:

```
Agent Provides Two Categories of Data
══════════════════════════════════════

Category 1: LIGHTNING CREDENTIALS (private, local)
  ├── LND host address     (e.g. localhost:10009)
  ├── tls.cert file        (proves LND's identity)
  └── admin.macaroon file  (auth token to operate LND)

  → Goes to: Financial Pod ONLY
  → Never touches: Nostr, SDK, or any remote server
  → Reason: These are keys to the agent's money

Category 2: AGENT PROFILE (public, global)
  ├── Agent name / alias   (e.g. "Alice GPU Provider")
  ├── Service kind         (e.g. 5001 = video transcription)
  ├── Price in msat        (e.g. 50000 = 50 sats)
  └── Description / tags   (what services are offered)

  → Goes to: Nostr relay (public, discoverable)
  → Handled by: Python SDK (nostr_sdk_wrapper)
  → Reason: Other agents need to discover you
```

---

## The Exact Data Flow — Frontend Onboarding

```
New Agent (on their device)
│
│  Opens frontend in browser
│
▼
┌─────────────────────────────────────────────────┐
│              FRONTEND (Next.js)                  │
│                                                   │
│  Section 1: Lightning Setup                       │
│  ┌─────────────────────────────────────────┐    │
│  │  LND Host:   [localhost:10009        ]  │    │
│  │  TLS Cert:   [Upload tls.cert...     ]  │    │
│  │  Macaroon:   [Upload admin.macaroon..]  │    │
│  └─────────────────────────────────────────┘    │
│                                                   │
│  Section 2: Agent Profile (goes to Nostr)         │
│  ┌─────────────────────────────────────────┐    │
│  │  Display Name: [Alice GPU Provider   ]  │    │
│  │  Service Type: [5001 - Video Transcr.]  │    │
│  │  Price (sats): [50                   ]  │    │
│  │  Description:  [Fast GPU inference...] │    │
│  └─────────────────────────────────────────┘    │
│                                                   │
│  [Connect & Register]                             │
└─────────────────────────────────────────────────┘
         │                        │
         │ (two separate calls)   │
         │                        │
         ▼                        ▼
┌─────────────────┐    ┌──────────────────────┐
│  Financial Pod  │    │    Python SDK         │
│  (Go daemon)    │    │  (nostr_sdk_wrapper)  │
│                 │    │                       │
│  Receives:      │    │  Receives:            │
│  • lnd_host     │    │  • agent_name         │
│  • tls_cert     │    │  • service_kind       │
│  • macaroon     │    │  • price_msat         │
│                 │    │  • description        │
│  Does:          │    │                       │
│  1. Save creds  │    │  Does:                │
│     to local    │    │  1. Generate Nostr    │
│     disk (0600) │    │     keypair           │
│  2. Connect to  │    │  2. Publish kind:0    │
│     agent's LND │    │     (profile)         │
│  3. Call GetInfo│    │  3. Publish kind:31990│
│  4. Return LND  │    │     (service listing) │
│     pubkey +    │    │  4. Return npub       │
│     alias       │    │                       │
└────────┬────────┘    └──────────┬────────────┘
         │                        │
         │                        ▼
         │              ┌──────────────────────┐
         │              │    Nostr Relay        │
         │              │   (public network)    │
         │              │                       │
         │              │  Stores:              │
         │              │  • kind:0 profile     │
         │              │  • kind:31990 listing │
         │              │  (discoverable by all)│
         │              └──────────────────────┘
         │
         ▼
┌─────────────────┐
│  Agent's LND    │
│  (their node)   │
│                 │
│  FP can now:    │
│  • Create HODL  │
│    invoices     │
│  • Pay invoices │
│  • Settle HTLCs │
└─────────────────┘
```

---

## Answer: Does Lightning Come Through SDK or Direct from Frontend?

**Direct from Frontend to Financial Pod — NOT through SDK.**

The SDK never sees the Lightning credentials. Here is the exact reason:

```
Frontend
  │
  ├──── POST /api/provision ────────────────────► Financial Pod
  │     {                                          (Go daemon, local)
  │       lnd_host: "localhost:10009",
  │       tls_cert_base64: "LS0tLS1CRUd...",      FP saves to disk:
  │       macaroon_base64: "AgEDbG5kAq...",    →  /etc/kuberbolt/tls.cert
  │     }                                          /etc/kuberbolt/admin.macaroon
  │                                                (chmod 600 — only FP can read)
  │
  └──── POST /api/register ─────────────────────► Python SDK
        {                                          (nostr_sdk_wrapper)
          agent_name: "Alice GPU Provider",
          service_kind: 5001,
          price_msat: 50000,
        }                                     →   Publishes to Nostr relay
                                                  (public information only)
```

**Why not through SDK?**
- The SDK runs in Python and communicates with Nostr relays over the internet
- Passing the macaroon through the SDK would mean it travels over the network
- The FP is always local to the agent's machine — it's the safe place for secrets
- The FP directly reads/writes to disk and talks to LND over a local connection

---

## How It Works Across Different Devices / People

This is the key design question. Each person (device) runs their own complete stack:

```
Person A (Alice — Provider)          Person B (Bob — Client)
on Machine A                         on Machine B
┌───────────────────────────┐        ┌───────────────────────────┐
│                           │        │                           │
│  Browser                  │        │  Browser                  │
│  └── Frontend (port 3000) │        │  └── Frontend (port 3000) │
│                           │        │                           │
│  Python SDK               │        │  Python SDK               │
│  └── nostr_sdk_wrapper    │        │  └── nostr_sdk_wrapper    │
│                           │        │                           │
│  Python Brain             │        │  Python Brain             │
│  └── LangChain Agent      │        │  └── LangChain Agent      │
│                           │        │                           │
│  Go Financial Pod         │        │  Go Financial Pod         │
│  └── Talks to Alice's LND │        │  └── Talks to Bob's LND   │
│                           │        │                           │
│  Alice's LND Node         │        │  Bob's LND Node           │
│  └── Alice's wallet       │        │  └── Bob's wallet         │
│                           │        │                           │
└───────────────────────────┘        └───────────────────────────┘
         │                                       │
         └──────────────── Nostr ────────────────┘
                    (public relay — shared)
                    Alice's listing: kind:31990
                    Bob finds Alice via discovery
```

**Every person runs their own isolated stack.** Nothing is shared except:
- The Nostr relay (public, read by everyone)
- The Lightning Network channels (standard Bitcoin Lightning)

---

## The Complete Onboarding Sequence (Option 5 in Full)

### For Alice (new Provider agent):

```
Step 1: Alice downloads the agent-pod docker-compose
        docker compose -f docker-compose.pod.yml up -d
        → Starts: LND node, Financial Pod, Brain, Frontend

Step 2: Alice opens browser → http://localhost:3000

Step 3: Alice fills the onboarding form:
        Lightning section:
          LND Host: localhost:10009 (or her cloud VPS address)
          TLS Cert: [she clicks upload, selects tls.cert from ~/.lnd/]
          Macaroon:  [she clicks upload, selects admin.macaroon]

        Profile section:
          Display Name: "Alice GPU Provider"
          Service Type: Video Transcription (5001)
          Price: 50 sats per job

Step 4: Frontend makes TWO calls:

        Call 1 → Financial Pod (Go):
        POST http://localhost:6001/provision
        {
          "lnd_host": "localhost:10009",
          "tls_cert_base64": "<file contents>",
          "macaroon_base64": "<file contents>"
        }

        Financial Pod:
        a. Saves cert + macaroon to /etc/kuberbolt/ (chmod 600)
        b. Dials LND: grpc.Dial("localhost:10009", tlsCreds, macCreds)
        c. Calls GetInfo → confirms LND is reachable
        d. Returns: { lnd_pubkey: "02abc...", lnd_alias: "User1_Alice" }

        Call 2 → Python SDK:
        POST http://localhost:8080/register
        {
          "agent_name": "Alice GPU Provider",
          "service_kind": 5001,
          "price_msat": 50000,
          "lnd_pubkey": "02abc..."    ← returned from FP in step above
        }

        Python SDK:
        a. Generates Nostr secp256k1 keypair
        b. Publishes kind:0 (profile event) to relay
        c. Publishes kind:31990 (service listing) to relay
           Tags: ["k","5001"], ["price","50000"], ["network","lightning"]
        d. Returns: { npub: "npub1alice...", nsec: "nsec1..." }

Step 5: Frontend shows Alice her identity:
        ✓ LND Connected: alias=User1_Alice, pubkey=02abc...
        ✓ Nostr Registered: npub1alice...
        ✓ Service Listed: kind:31990 live on relay
        ⚠ Save your nsec key securely — it's shown only once

Step 6: Alice is now on the network.
        Bob can discover her via kind:31990 query.
        When Bob requests a job → Alice's FP handles L402 automatically.
```

---

## Data Responsibility Summary

| Data | Collected By | Stored At | Sent To | Who Can See |
|---|---|---|---|---|
| `tls.cert` | Frontend (upload) | FP local disk only | FP only | Only FP process |
| `admin.macaroon` | Frontend (upload) | FP local disk only | FP only | Only FP process |
| `lnd_host` | Frontend (input) | FP config file | FP only | Only FP process |
| `agent_name` | Frontend (input) | Nostr relay | Nostr SDK → Relay | Everyone |
| `service_kind` | Frontend (input) | Nostr relay | Nostr SDK → Relay | Everyone |
| `price_msat` | Frontend (input) | Nostr relay | Nostr SDK → Relay | Everyone |
| `lnd_pubkey` | FP (from GetInfo) | Nostr relay | SDK → Relay | Everyone |
| `nsec` (Nostr key) | SDK (generated) | Agent's device | Shown to agent once | Agent only |
| `npub` (Nostr key) | SDK (generated) | Nostr relay | SDK → Relay | Everyone |

---

## Cross-Device Compatibility

For this to work on any device, the docker-compose stack must be self-contained:

```yaml
# docker-compose.pod.yml — runs identically on any machine

services:
  lnd:
    image: lightninglabs/lnd:v0.18.0-beta
    ports:
      - "10009:10009"    # gRPC
    volumes:
      - lnd_data:/root/.lnd

  financial-pod:
    image: kuberbolt/financial-pod
    ports:
      - "6001:6001"      # Provision API + gRPC service
    volumes:
      - fp_config:/etc/kuberbolt    # persists creds across restarts
    depends_on:
      - lnd

  brain:
    image: kuberbolt/brain
    environment:
      FP_HOST: financial-pod:6001
    depends_on:
      - financial-pod

  sdk:
    image: kuberbolt/sdk
    ports:
      - "8080:8080"      # Registration API
    environment:
      NOSTR_RELAY: wss://relay.kuberbolt.network

  frontend:
    image: kuberbolt/frontend
    ports:
      - "3000:3000"      # Browser UI
    environment:
      FP_API: http://financial-pod:6001
      SDK_API: http://sdk:8080

volumes:
  lnd_data:      # LND wallet, channels, macaroons
  fp_config:     # FP's copy of credentials (encrypted at rest)
```

**Anyone on any OS** (Windows, Mac, Linux) can run:
```bash
docker compose up -d
# → open http://localhost:3000
# → fill in the form
# → done
```

The tls.cert and macaroon are generated fresh by the LND container on first start,
so each person gets their own unique credentials automatically.

---

## One-Line Summary of the Architecture

> **Frontend collects both Lightning and profile data. Lightning credentials go directly to the Financial Pod (local, never leaves the machine). Profile data goes to the Python SDK which publishes it to Nostr. The two flows are completely separate and the macaroon is never transmitted over any network.**
