# Agent Onboarding — How a New Agent Links Their Lightning Node

This document explains exactly how a brand new agent joins the Kuberbolt network,
connects their Lightning credentials, and becomes a functioning participant.

---

## The Core Mental Model

**Kuberbolt is non-custodial.** This means:
- Kuberbolt NEVER holds anyone's funds
- Kuberbolt NEVER owns anyone's LND node
- Each agent runs their OWN LND node
- Each agent gives their Financial Pod the CREDENTIALS to talk to their node
- The FP talks to the agent's LND on their behalf — like a trusted local accountant

```
Agent A (new user)                    The Kuberbolt Network
┌──────────────────────────────┐      ┌─────────────────────────┐
│                              │      │                         │
│  Agent A's LND Node          │      │  Nostr Relay            │
│  (Alice controls this)       │      │  (public, anyone)       │
│  ├── tls.cert                │      │                         │
│  ├── admin.macaroon          │      │  Agent B's FP           │
│  └── Channel to network      │      │  (Bob)                  │
│                              │      │                         │
│  Agent A's Financial Pod     │      │  Agent C's FP           │
│  (reads Alice's credentials) │      │  (Charlie)              │
│  └── Talks to Alice's LND   │      │                         │
│                              │      └─────────────────────────┘
└──────────────────────────────┘
```

So the question is: **how does a new agent give their LND credentials to their own Financial Pod?**

---

## Option 1: Local Deployment (Same Machine)

This is the simplest and most common case — the agent runs their LND and their FP on the **same machine** (or same Docker network).

### Setup Flow

```
New Agent (Alice)
│
├── Step 1: Spin up LND
│   docker compose -f lightning-infra/docker-compose.lnd.yml up -d
│   → Creates: /root/.lnd/tls.cert
│             /root/.lnd/data/chain/bitcoin/regtest/admin.macaroon
│
├── Step 2: Configure Financial Pod
│   Set environment variables pointing to her LND:
│   
│   LND_HOST=localhost:10009          ← or kuberbolt-lnd:10009 in Docker
│   LND_TLS_CERT_PATH=/root/.lnd/tls.cert
│   LND_MACAROON_PATH=/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon
│
└── Step 3: Start Financial Pod
    go run cmd/financialpod/main.go
    → FP reads the credentials
    → FP connects to Alice's LND
    → FP registers Alice on Nostr
    → Alice is now on the network
```

### In Code: How the FP Reads Credentials at Startup

```go
// cmd/financialpod/main.go — startup sequence

func main() {
    // 1. Load config (from env vars or config file)
    cfg := config.Load()
    // cfg.LNDHost         = "localhost:10009"
    // cfg.TLSCertPath     = "/root/.lnd/tls.cert"
    // cfg.MacaroonPath    = "/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon"
    
    // 2. Connect to THIS AGENT'S LND node
    lndClient, err := ln.NewClient(cfg.LNDHost, cfg.TLSCertPath, cfg.MacaroonPath)
    if err != nil {
        log.Fatalf("Failed to connect to LND: %v", err)
    }
    
    // 3. Verify the connection works
    info, err := lndClient.GetInfo(context.Background())
    if err != nil {
        log.Fatalf("LND not reachable: %v", err)
    }
    log.Printf("Connected to LND node: %s (pubkey: %s)", 
        info.Alias, info.IdentityPubkey)
    
    // 4. Start the Financial Pod server
    fp := financialpod.New(lndClient, ledger, nostrClient)
    fp.Start()
}
```

### Docker Volume Mount (most common setup)

```yaml
# agent-pod/docker-compose.pod.yml

services:
  financial-pod:
    image: kuberbolt/financial-pod
    environment:
      # Point to the LND container on the same Docker network
      LND_HOST: "kuberbolt-lnd:10009"
      LND_TLS_CERT_PATH: "/lnd-data/tls.cert"
      LND_MACAROON_PATH: "/lnd-data/data/chain/bitcoin/regtest/admin.macaroon"
    volumes:
      # Mount Alice's LND data directory into the FP container
      - lnd_data:/lnd-data:ro   # ← read-only mount of LND's volume

  brain:
    image: kuberbolt/brain
    environment:
      FP_HOST: "financial-pod:6001"

volumes:
  lnd_data:
    external: true   # already created by LND container
```

**What happens**: Both the LND container and the FP container share the same Docker volume. The FP reads the cert and macaroon files directly from that shared volume. No manual copying needed.

---

## Option 2: Remote LND Node (Different Machine)

This is for power users who run LND on a dedicated server (e.g., a VPS) and their Financial Pod on a different machine.

### The Problem

You can't just copy `tls.cert` and `admin.macaroon` over plaintext — that would expose your LND credentials. You need to:
1. Securely transfer the credentials
2. Store them safely on the FP machine

### The Solution: `export-credentials.sh` + Secure Transfer

```
Machine 1 (LND server — VPS)          Machine 2 (FP + Brain — local)
┌──────────────────────────┐           ┌──────────────────────────┐
│                          │           │                          │
│  LND running             │           │  Financial Pod           │
│                          │           │  (needs creds)           │
│  Run export script:      │           │                          │
│  export-credentials.sh   │           │                          │
│  → encrypts tls.cert +   │           │                          │
│    macaroon into:        │           │                          │
│    lnd_backup.tar.enc    │           │                          │
│                          │           │                          │
│  Transfer via SCP/SFTP:  │──────────►│                          │
│  (encrypted, safe)       │           │  Decrypt + place files:  │
│                          │           │  restore-credentials.sh  │
└──────────────────────────┘           │  → /etc/kuberbolt/lnd/   │
                                       │    tls.cert              │
                                       │    admin.macaroon        │
                                       └──────────────────────────┘
```

The FP on Machine 2 is then configured:
```bash
LND_HOST=<VPS_IP>:10009
LND_TLS_CERT_PATH=/etc/kuberbolt/lnd/tls.cert
LND_MACAROON_PATH=/etc/kuberbolt/lnd/admin.macaroon
```

### Important: Firewall on the LND Server

You must open port `10009` on the VPS firewall, but **only for the FP machine's IP**:
```bash
# On the VPS — only allow the FP machine to connect to LND gRPC
ufw allow from <FP_MACHINE_IP> to any port 10009
```

Never expose port 10009 to the public internet.

---

## Option 3: Custom Baked Macaroon (Least Privilege)

Instead of giving the FP the `admin.macaroon` (which has ALL permissions), you can bake a **restricted macaroon** that only allows the specific operations the FP needs.

### What Permissions the FP Actually Needs

```
Operation                   Macaroon Permission
─────────────────────────   ──────────────────
Create HODL invoice         invoices:write
Settle HODL invoice         invoices:write
Cancel HODL invoice         invoices:write
Watch invoice state         invoices:read
Send payment                offchain:write
Read channel info           info:read
Read wallet balance         onchain:read
```

### Baking a Restricted Macaroon via lncli

```bash
# Inside the LND container
docker exec -it kuberbolt-lnd lncli \
    --network=regtest \
    bakemacaroon \
    invoices:write \
    invoices:read \
    offchain:write \
    info:read \
    onchain:read \
    > fp-restricted.macaroon
```

Now give this restricted macaroon to the FP instead of `admin.macaroon`. If the FP is ever compromised, the attacker can only do those specific operations — they can't drain the wallet or change settings.

---

## Option 4: Polar (Local Dev / Testing)

For development, Polar is the easiest way for a new agent to get started. Polar is a GUI app that manages regtest LND nodes.

```
New Agent installs Polar
→ Creates a network (1-click)
→ Polar creates LND nodes with wallets already funded
→ Credentials are at: C:\Users\<name>\.polar\networks\<id>\volumes\lnd\<node>\

tls.cert:      ~/.polar/networks/1/volumes/lnd/alice/tls.cert
admin.macaroon: ~/.polar/networks/1/volumes/lnd/alice/data/chain/bitcoin/regtest/admin.macaroon

Point your FP at these paths:
LND_HOST=localhost:10001  (Polar's default port for first node)
LND_TLS_CERT_PATH=~/.polar/networks/1/volumes/lnd/alice/tls.cert
LND_MACAROON_PATH=~/.polar/networks/1/volumes/lnd/alice/data/chain/bitcoin/regtest/admin.macaroon
```

---

## Option 5: Interactive Onboarding (Frontend Flow)

This is what the SRS envisions for non-technical users. The Frontend walks the agent through it:

```
Frontend (Next.js)                          Financial Pod API
     │                                            │
     │  New Agent opens the UI                    │
     │  Fills in a form:                          │
     │  ┌────────────────────────────────────┐    │
     │  │  Your LND Connection               │    │
     │  │  ─────────────────────────────     │    │
     │  │  LND Host:     [____________]      │    │
     │  │  TLS Cert:     [Upload file...]    │    │
     │  │  Macaroon:     [Upload file...]    │    │
     │  │                                    │    │
     │  │  Agent Name:   [Alice]             │    │
     │  │  Service Kind: [5001 - Video]      │    │
     │  │  Price (sats): [50]               │    │
     │  │                                    │    │
     │  │  [Connect & Register]              │    │
     │  └────────────────────────────────────┘    │
     │                                            │
     │── POST /api/provision ──────────────────►  │
     │   { lndHost, tlsCertBase64,               │
     │     macaroonBase64, agentName,             │
     │     serviceKind, priceMSat }               │
     │                                            │
     │                           FP does:         │
     │                           1. Decode cert+mac from base64
     │                           2. Save to secure local storage
     │                           3. Try LND connection → verify
     │                           4. Generate Nostr keypair
     │                           5. Publish kind:0 profile
     │                           6. Publish kind:31990 listing
     │                           7. Return success + npub
     │                                            │
     │◄── { success: true, npub: "npub1..." } ──│
     │                                            │
     │  Agent is now registered!                  │
```

### The Provision Endpoint Code

```go
// financial-pod/internal/gateway/provision.go

type ProvisionRequest struct {
    LNDHost       string `json:"lnd_host"`
    TLSCertBase64 string `json:"tls_cert_base64"`
    MacaroonBase64 string `json:"macaroon_base64"`
    AgentName     string `json:"agent_name"`
    ServiceKind   int    `json:"service_kind"`
    PriceMSat     int64  `json:"price_msat"`
}

func (fp *FinancialPod) Provision(req *ProvisionRequest) (*ProvisionResponse, error) {
    // 1. Decode credentials from base64
    tlsCert, err := base64.StdEncoding.DecodeString(req.TLSCertBase64)
    macaroon, err := base64.StdEncoding.DecodeString(req.MacaroonBase64)
    
    // 2. Save to secure local path (not world-readable)
    os.WriteFile("/etc/kuberbolt/tls.cert", tlsCert, 0600)
    os.WriteFile("/etc/kuberbolt/admin.macaroon", macaroon, 0600)
    
    // 3. Test the connection immediately
    lndClient, err := ln.NewClient(req.LNDHost, "/etc/kuberbolt/tls.cert", 
        "/etc/kuberbolt/admin.macaroon")
    if err != nil {
        return nil, fmt.Errorf("could not connect to LND: %w", err)
    }
    
    info, err := lndClient.GetInfo(context.Background())
    if err != nil {
        return nil, fmt.Errorf("LND connection test failed: %w", err)
    }
    
    // 4. Generate Nostr identity
    keypair := nostr.GenerateKeyPair()
    
    // 5. Publish agent to Nostr relay
    fp.nostr.PublishProfile(keypair, req.AgentName)
    fp.nostr.PublishListing(keypair, req.ServiceKind, req.PriceMSat)
    
    // 6. Store everything in config
    fp.config.Save(&Config{
        LNDHost:     req.LNDHost,
        LNDNodeAlias: info.Alias,
        LNDPubkey:   info.IdentityPubkey,
        NostrPubkey: keypair.PublicKey,
        AgentName:   req.AgentName,
    })
    
    return &ProvisionResponse{
        Success:     true,
        NPub:        keypair.NPub,
        LNDPubkey:   info.IdentityPubkey,
        LNDAlias:    info.Alias,
    }, nil
}
```

---

## Summary: Which Option for Which Situation

| Situation | Recommended Option |
|---|---|
| Developer testing locally | **Option 4** — Polar (easiest, GUI, 1-click) |
| Developer using Docker | **Option 1** — Docker volume mount (automated) |
| Production, same machine | **Option 1** — env vars pointing to local LND |
| Production, separate machines | **Option 2** — export-credentials + secure transfer |
| Security-conscious user | **Option 3** — baked restricted macaroon |
| Non-technical end user | **Option 5** — Frontend onboarding UI (to be built) |

---

## The Critical Security Rule

> **The Financial Pod never sends Lightning credentials over the network.**
> It only READS them from local disk and uses them to call the local LND.
> The macaroon never leaves the machine it was set up on.

This is what makes the system non-custodial — Kuberbolt infrastructure never touches
or sees anyone's macaroon. The FP is always co-located with or directly connected to
the agent's own LND node.
