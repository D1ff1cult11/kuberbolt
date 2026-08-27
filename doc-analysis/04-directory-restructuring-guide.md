# Directory Restructuring — Detailed Migration Guide

This document specifies every file move, rename, merge, creation, and deletion
required to transform the current workspace into the canonical `agent-payment-network/` structure.

---

## Current Directory Layout (what exists now)

```
kuberbolt-workspace/
├── kuberbolt/                           # Separate git clone (has .git/)
│   ├── .git/
│   ├── .gitignore, LICENSE, README.md, CODE_OF_CONDUCT.md, CONTRIBUTING.md
│   ├── SRS.md                           # Phase II SRS (280 lines)
│   ├── client/                          # ALL EMPTY STUBS
│   ├── gatekeeper/                      # ALL EMPTY STUBS
│   ├── proto/                           # ALL EMPTY (0 bytes)
│   ├── examples/                        # ALL EMPTY (0 bytes)
│   └── scripts/                         # EMPTY directory
│
└── mock_work/
    ├── SRS.md                           # Original SRS (256 lines)
    ├── docker-compose.yml               # BROKEN (port collisions)
    ├── Dockerfile.fp                    # Outdated
    ├── Dockerfile.sdk                   # Outdated
    ├── client.go                        # Standalone client script
    ├── demo_htlc.go                     # Go demo (won't compile)
    ├── demo_macaroon.go                 # Go demo (won't compile)
    ├── demo_htlc.py                     # Python demo
    ├── demo_macaroon.py                 # Python demo
    │
    ├── fp/                              # Financial Pod (partially working)
    │   ├── go.mod, go.sum
    │   ├── main.go                      # Skeleton
    │   ├── demo_ledger.go               # Working demo
    │   ├── demo_ledger.db               # Test artifact
    │   ├── ledger/db.go                 # ✅ WORKING (pure Go SQLite)
    │   └── lnd/                         # EMPTY directory
    │
    ├── gatekeeper/                      # Financial Pod v2 (doesn't compile)
    │   ├── go.mod, go.sum
    │   ├── main.go                      # CLI entrypoint
    │   ├── config/config.go             # YAML config + keygen
    │   ├── financial/
    │   │   ├── financial_pod.go         # L402 interceptor + RPCs (295 lines)
    │   │   ├── budget_manager.go        # Budget enforcement
    │   │   └── invoice_cache.go         # TTL cache
    │   ├── macaroon/manager.go          # Macaroon create/verify
    │   ├── lnd/client.go                # LND gRPC client (broken)
    │   ├── nostr/client.go              # Nostr publish only
    │   ├── ledger/ledger.go             # Event ledger (CGO, won't compile)
    │   └── pb/                          # Generated from wrong proto
    │
    ├── sdk/                             # Python SDK stub
    │   ├── main.py                      # Fake (hardcoded data)
    │   └── requirements.txt
    │
    ├── agents/                          # Python agent scripts
    │   ├── client_agent.py              # Fake (sleep + log)
    │   └── provider_agent.py            # Fake (sleep + log)
    │
    ├── proto/
    │   ├── kuberbolt.proto              # Correct proto (151 lines)
    │   └── service.proto                # Old placeholder proto
    │
    ├── scripts/
    │   ├── generate-mtls-certs.sh       # mTLS cert generator
    │   └── init-regtest.sh              # 3-node regtest init
    │
    ├── polar/
    │   └── setup-polar-automated.sh     # Polar setup helper
    │
    ├── client/                          # Old generated proto stubs
    │   ├── main.py, service_pb2.py, service_pb2_grpc.py
    │   └── kuberbolt/agent.py
    │
    ├── cfo/                             # Just .gitkeep
    ├── compute/                         # Just .gitkeep
    │
    └── kuberbolt/                       # Nested repo clone (has .git/)
        ├── .git/, .gitignore, LICENSE, README.md, etc.
        ├── SRS.md                       # Phase II SRS (17693 bytes)
        ├── client/                      # ALL EMPTY STUBS
        ├── gatekeeper/                  # ALL EMPTY STUBS
        ├── proto/                       # ALL EMPTY (0 bytes)
        ├── examples/                    # ALL EMPTY (0 bytes)
        └── lightning node/              # ✅ REAL WORKING CODE
            ├── docker-compose.yml       # Bitcoind + 2 LND nodes
            ├── go.mod
            ├── main.go                  # Automated 2-node setup
            ├── pay.go                   # Payment with guardrail
            ├── test-data.json           # Live credentials
            ├── README.md
            ├── terminal run commands.txt
            ├── config/types.go
            ├── docker/client.go         # Docker exec helpers
            ├── scripts/
            │   ├── auto-open-channel.sh
            │   ├── peer-setup.sh
            │   ├── backup_lnd_creds.sh
            │   └── restore_lnd_creds.sh
            └── templates/
                ├── lnd-single-compose.yml
                └── README-LND-peer.md
```

---

## Target Directory Layout

```
agent-payment-network/
├── README.md
├── ARCHITECTURE.md
├── LICENSE
├── .gitignore
├── .env.example
│
├── docs/
│   ├── agent-payment-network-srs.md
│   ├── local-dev-setup.md
│   └── diagrams/
│
├── sdk/
│   └── python/
│       ├── nostr_sdk_wrapper/
│       │   ├── __init__.py
│       │   ├── identity.py
│       │   ├── profile.py
│       │   ├── listing.py
│       │   ├── discovery.py
│       │   ├── dm.py
│       │   └── feedback.py
│       ├── pyproject.toml
│       └── tests/
│
├── agent-pod/
│   ├── brain/
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── langchain_agent.py
│   │   │   └── financial_pod_client.py
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   │
│   ├── financial-pod/
│   │   ├── cmd/financialpod/main.go
│   │   ├── internal/
│   │   │   ├── ln/client.go
│   │   │   ├── l402/
│   │   │   │   ├── macaroon.go
│   │   │   │   └── interceptor.go
│   │   │   ├── ledger/db.go
│   │   │   ├── gateway/server.go
│   │   │   ├── requester/client.go
│   │   │   ├── config/config.go
│   │   │   ├── budget/manager.go
│   │   │   └── cache/invoice.go
│   │   ├── go.mod
│   │   └── Dockerfile
│   │
│   ├── proto/
│   │   └── agent_service.proto
│   └── docker-compose.pod.yml
│
├── lightning-infra/
│   ├── docker-compose.lnd.yml
│   ├── config/
│   │   ├── lnd.conf
│   │   └── bitcoin.conf
│   ├── scripts/
│   │   ├── init-wallet.sh
│   │   ├── open-channel.sh
│   │   ├── export-credentials.sh
│   │   ├── restore-credentials.sh
│   │   └── peer-setup.sh
│   ├── tools/                           # Go automation tools
│   │   ├── go.mod
│   │   ├── main.go
│   │   ├── pay.go
│   │   ├── config/types.go
│   │   └── docker/client.go
│   └── polar-exports/
│       └── setup-polar-automated.sh
│
├── shared/
│   ├── proto/
│   │   └── kuberbolt.proto
│   └── nostr-kinds.md
│
├── scripts/
│   ├── deploy-pod.sh
│   ├── e2e-test.sh
│   └── generate-mtls-certs.sh
│
└── .github/workflows/
    ├── ci-go.yml
    └── ci-python.yml
```

---

## File-by-File Migration Commands

Below is every operation needed, in execution order.

### Step 0: Create the target root

```powershell
New-Item -ItemType Directory -Path "d:\Dev Projects\kuberbolt-workspace\agent-payment-network"
```

### Step 1: Root files

| Action | Source → Target |
|---|---|
| COPY | `mock_work/kuberbolt/README.md` → `agent-payment-network/README.md` |
| COPY | `mock_work/kuberbolt/LICENSE` → `agent-payment-network/LICENSE` |
| COPY | `mock_work/kuberbolt/.gitignore` → `agent-payment-network/.gitignore` |
| CREATE | `agent-payment-network/ARCHITECTURE.md` (new) |
| CREATE | `agent-payment-network/.env.example` (new) |

### Step 2: docs/

| Action | Source → Target |
|---|---|
| COPY | `mock_work/SRS.md` → `agent-payment-network/docs/agent-payment-network-srs.md` |
| CREATE | `agent-payment-network/docs/local-dev-setup.md` (merge lightning README + peer README) |
| CREATE | `agent-payment-network/docs/diagrams/` (empty for now) |

### Step 3: lightning-infra/

| Action | Source → Target |
|---|---|
| COPY | `mock_work/kuberbolt/lightning node/docker-compose.yml` → `lightning-infra/docker-compose.lnd.yml` |
| COPY | `mock_work/kuberbolt/lightning node/scripts/auto-open-channel.sh` → `lightning-infra/scripts/open-channel.sh` |
| COPY | `mock_work/kuberbolt/lightning node/scripts/peer-setup.sh` → `lightning-infra/scripts/peer-setup.sh` |
| COPY | `mock_work/kuberbolt/lightning node/scripts/backup_lnd_creds.sh` → `lightning-infra/scripts/export-credentials.sh` |
| COPY | `mock_work/kuberbolt/lightning node/scripts/restore_lnd_creds.sh` → `lightning-infra/scripts/restore-credentials.sh` |
| COPY | `mock_work/kuberbolt/lightning node/templates/lnd-single-compose.yml` → `lightning-infra/config/lnd-single-compose.yml` |
| COPY | `mock_work/kuberbolt/lightning node/main.go` → `lightning-infra/tools/main.go` |
| COPY | `mock_work/kuberbolt/lightning node/pay.go` → `lightning-infra/tools/pay.go` |
| COPY | `mock_work/kuberbolt/lightning node/config/types.go` → `lightning-infra/tools/config/types.go` |
| COPY | `mock_work/kuberbolt/lightning node/docker/client.go` → `lightning-infra/tools/docker/client.go` |
| COPY | `mock_work/kuberbolt/lightning node/go.mod` → `lightning-infra/tools/go.mod` |
| COPY | `mock_work/kuberbolt/lightning node/test-data.json` → `lightning-infra/tools/test-data.json` |
| COPY | `mock_work/polar/setup-polar-automated.sh` → `lightning-infra/polar-exports/setup-polar-automated.sh` |
| CREATE | `lightning-infra/scripts/init-wallet.sh` (new, from init-regtest.sh logic) |
| CREATE | `lightning-infra/config/lnd.conf` (extract LND flags from compose) |
| CREATE | `lightning-infra/config/bitcoin.conf` (extract bitcoind flags from compose) |

**Go module path update**: `lightning-infra/tools/go.mod` module path must change from `github.com/devlup-labs/kuberbolt/lightning-node` to `github.com/kuberbolt/lightning-infra/tools`. All import paths in `main.go`, `pay.go` must update accordingly.

### Step 4: agent-pod/financial-pod/ (MERGE of fp/ + gatekeeper/)

| Action | Source → Target | Notes |
|---|---|---|
| COPY | `mock_work/gatekeeper/main.go` → `financial-pod/cmd/financialpod/main.go` | Better entrypoint (config, signals) |
| COPY | `mock_work/fp/ledger/db.go` → `financial-pod/internal/ledger/db.go` | Working pure-Go SQLite |
| COPY | `mock_work/gatekeeper/lnd/client.go` → `financial-pod/internal/ln/client.go` | Needs TLS/macaroon fix |
| COPY | `mock_work/gatekeeper/macaroon/manager.go` → `financial-pod/internal/l402/macaroon.go` | Needs caveat fix |
| EXTRACT | `mock_work/gatekeeper/financial/financial_pod.go` L100-166 → `financial-pod/internal/l402/interceptor.go` | L402 interceptor logic |
| EXTRACT | `mock_work/gatekeeper/financial/financial_pod.go` L167-247 → `financial-pod/internal/gateway/server.go` | Service-side RPCs |
| COPY | `mock_work/gatekeeper/financial/budget_manager.go` → `financial-pod/internal/budget/manager.go` | Needs underflow fix |
| COPY | `mock_work/gatekeeper/financial/invoice_cache.go` → `financial-pod/internal/cache/invoice.go` | Needs unused import fix |
| COPY | `mock_work/gatekeeper/config/config.go` → `financial-pod/internal/config/config.go` | Needs bech32 fix |
| COPY | `mock_work/gatekeeper/nostr/client.go` → `financial-pod/internal/nostr/client.go` | Needs subscribe support |
| ADAPT | `mock_work/fp/go.mod` → `financial-pod/go.mod` | Use as base, add gatekeeper deps |
| ADAPT | `mock_work/Dockerfile.fp` → `financial-pod/Dockerfile` | Update paths |

**Go module path**: `github.com/kuberbolt/financial-pod`
All internal imports update: `github.com/kuberbolt/financial-pod/internal/ln`, etc.

### Step 5: agent-pod/proto/

| Action | Source → Target |
|---|---|
| COPY | `mock_work/proto/kuberbolt.proto` → `agent-payment-network/agent-pod/proto/agent_service.proto` |
| COPY | `mock_work/proto/kuberbolt.proto` → `agent-payment-network/shared/proto/kuberbolt.proto` |

Rename `go_package` option inside the proto file to match new module paths.

### Step 6: agent-pod/brain/ (Python Agent)

| Action | Source → Target | Notes |
|---|---|---|
| CREATE | `brain/app/main.py` | New (real LangChain agent entry point) |
| CREATE | `brain/app/langchain_agent.py` | New (LangChain tools wrapping SDK + FP) |
| CREATE | `brain/app/financial_pod_client.py` | New (gRPC client to local FP) |
| ADAPT | `mock_work/sdk/requirements.txt` → `brain/requirements.txt` | Add langchain, grpcio |
| ADAPT | `mock_work/Dockerfile.sdk` → `brain/Dockerfile` | Update paths |

### Step 7: sdk/python/

| Action | Source → Target | Notes |
|---|---|---|
| CREATE | `sdk/python/nostr_sdk_wrapper/__init__.py` | New |
| CREATE | `sdk/python/nostr_sdk_wrapper/identity.py` | New |
| CREATE | `sdk/python/nostr_sdk_wrapper/profile.py` | New |
| CREATE | `sdk/python/nostr_sdk_wrapper/listing.py` | New |
| CREATE | `sdk/python/nostr_sdk_wrapper/discovery.py` | New |
| CREATE | `sdk/python/nostr_sdk_wrapper/dm.py` | New |
| CREATE | `sdk/python/nostr_sdk_wrapper/feedback.py` | New |
| ADAPT | `mock_work/kuberbolt/client/pyproject.toml` → `sdk/python/pyproject.toml` | Update deps |
| CREATE | `sdk/python/tests/` | New |

### Step 8: scripts/

| Action | Source → Target |
|---|---|
| COPY | `mock_work/scripts/generate-mtls-certs.sh` → `scripts/generate-mtls-certs.sh` |
| CREATE | `scripts/deploy-pod.sh` (new) |
| CREATE | `scripts/e2e-test.sh` (new) |

### Step 9: shared/

| Action | Source → Target |
|---|---|
| CREATE | `shared/nostr-kinds.md` (new — registry of kind:0, kind:31990, kind:7000, NIP-44) |

### Step 10: .github/workflows/

| Action | Source → Target |
|---|---|
| CREATE | `.github/workflows/ci-go.yml` (new) |
| CREATE | `.github/workflows/ci-python.yml` (new) |

---

## Files to DELETE After Migration

These files serve no purpose once migration is complete:

| Path | Reason |
|---|---|
| `mock_work/kuberbolt/` (entire nested folder) | All useful files extracted, rest is empty stubs |
| `mock_work/gatekeeper/` (entire folder) | Merged into `agent-pod/financial-pod/` |
| `mock_work/fp/` (entire folder) | Merged into `agent-pod/financial-pod/` |
| `mock_work/agents/` (entire folder) | Fake scripts, replaced by real brain |
| `mock_work/sdk/` (entire folder) | Fake stub, replaced by real SDK |
| `mock_work/client/` (entire folder) | Old generated stubs |
| `mock_work/cfo/` | Empty placeholder |
| `mock_work/compute/` | Empty placeholder |
| `mock_work/proto/service.proto` | Old placeholder proto |
| `mock_work/docker-compose.yml` | Broken, replaced by lightning-infra |
| `mock_work/Dockerfile.fp` | Replaced by new Dockerfiles |
| `mock_work/Dockerfile.sdk` | Replaced by new Dockerfiles |
| `mock_work/demo_htlc.go` | Go demo that doesn't compile |
| `mock_work/demo_macaroon.go` | Go demo that doesn't compile |
| `mock_work/client.go` | Standalone client, superseded |
| `kuberbolt/` (outer workspace clone) | Separate git repo, leave untouched |

### Files to ARCHIVE (keep for reference but not in main tree)

| Path | Reason |
|---|---|
| `mock_work/demo_htlc.py` | Python demo, useful reference |
| `mock_work/demo_macaroon.py` | Python demo, useful reference |
| `mock_work/fp/demo_ledger.go` | Working demo, useful reference |
| `mock_work/scripts/init-regtest.sh` | 3-node regtest script, useful reference |

Move these to `agent-payment-network/docs/archive/` or `docs/demos/`.

---

## Import Path Changes Summary

| Old Import Path | New Import Path |
|---|---|
| `github.com/kuberbolt/fp/ledger` | `github.com/kuberbolt/financial-pod/internal/ledger` |
| `github.com/kuberbolt/gatekeeper/config` | `github.com/kuberbolt/financial-pod/internal/config` |
| `github.com/kuberbolt/gatekeeper/financial` | `github.com/kuberbolt/financial-pod/internal/gateway` + `internal/requester` |
| `github.com/kuberbolt/gatekeeper/lnd` | `github.com/kuberbolt/financial-pod/internal/ln` |
| `github.com/kuberbolt/gatekeeper/macaroon` | `github.com/kuberbolt/financial-pod/internal/l402` |
| `github.com/kuberbolt/gatekeeper/nostr` | `github.com/kuberbolt/financial-pod/internal/nostr` |
| `github.com/kuberbolt/gatekeeper/ledger` | DELETED (use `internal/ledger` from fp/) |
| `github.com/kuberbolt/proto/v1` | `github.com/kuberbolt/financial-pod/proto` |
| `github.com/devlup-labs/kuberbolt/lightning-node/config` | `github.com/kuberbolt/lightning-infra/tools/config` |
| `github.com/devlup-labs/kuberbolt/lightning-node/docker` | `github.com/kuberbolt/lightning-infra/tools/docker` |
