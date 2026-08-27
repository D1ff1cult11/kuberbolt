# Current Code Inventory — What Is Implemented & How

This document catalogs every piece of real, functional code in the workspace, grouped by component.
Each entry includes the file path, what it does, how it works internally, and its current state.

---

## 1. SQLite Ledger (fp/ledger/db.go) — ✅ WORKING

**File**: `mock_work/fp/ledger/db.go` (110 lines)
**Language**: Go
**Status**: Compiles and runs on Windows. Verified via `demo_ledger.go`.

### What it does
Provides persistent financial record-keeping for a single Financial Pod. Stores three types of data:
- **Ledger transactions** — every payment sent or received (direction, amount, status, payment hash)
- **Payment holds** — HTLC hold invoice tracking (rhash ↔ preimage ↔ job mapping)
- **Service registry** — registered services with pricing

### How it works internally
- Opens a SQLite database using `modernc.org/sqlite` (pure Go, no CGO — critical for Windows)
- On startup, runs `initSchema()` which creates 3 tables via `CREATE TABLE IF NOT EXISTS`
- Exposes CRUD methods:
  - `RecordTransaction(tx)` — INSERT into ledger table
  - `UpdateTransactionStatus(txID, status, preimage)` — UPDATE status + settled_at timestamp
  - `RecordPaymentHold(hold)` — INSERT into payment_holds table
  - `GetPaymentHold(rhash)` — SELECT by rhash (used to look up preimage for settlement)
  - `Close()` — close database connection

### Schema

```sql
CREATE TABLE IF NOT EXISTS ledger (
    transaction_id TEXT PRIMARY KEY,
    direction TEXT NOT NULL,        -- 'incoming' or 'outgoing'
    agent_pubkey TEXT NOT NULL,
    amount_msat INTEGER NOT NULL,
    status TEXT NOT NULL,           -- 'pending', 'settled', 'cancelled'
    hold_invoice_hash TEXT,
    preimage TEXT,
    created_at DATETIME NOT NULL,
    settled_at DATETIME,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS payment_holds (
    hold_id TEXT PRIMARY KEY,
    rhash TEXT NOT NULL UNIQUE,
    preimage TEXT NOT NULL,
    htlc_timeout_blocks INTEGER NOT NULL,
    job_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS service_registry (
    service_id TEXT PRIMARY KEY,
    provider_pubkey TEXT NOT NULL,
    service_name TEXT NOT NULL,
    price_msat INTEGER NOT NULL,
    kind INTEGER NOT NULL,
    active BOOLEAN NOT NULL DEFAULT 1
);
```

### What's missing vs SRS §8
- No `counterparty_pubkey` column (SRS requires it)
- No `macaroon_id` column (SRS requires it)
- No `job_id` column in the ledger table (only in payment_holds)
- `direction` uses free text instead of enforced enum

---

## 2. Ledger Demo (fp/demo_ledger.go) — ✅ WORKING

**File**: `mock_work/fp/demo_ledger.go` (133 lines)
**Language**: Go
**Status**: Compiles and runs. Outputs correct state transitions.

### What it does
End-to-end demonstration of the HTLC state flow in the SQLite ledger:
1. Deletes any existing `demo_ledger.db`
2. Creates a fresh ledger
3. Generates a SHA-256 hash from a preimage (simulating HTLC creation)
4. Records a payment hold (rhash → preimage → job_id)
5. Records a PENDING transaction
6. Looks up the hold by rhash
7. Updates the transaction to SETTLED with the preimage
8. Prints all state transitions

---

## 3. Financial Pod Server Skeleton (fp/main.go) — ⚠️ PARTIAL

**File**: `mock_work/fp/main.go` (45 lines)
**Language**: Go
**Status**: Compiles but does nothing useful. Has dead imports.

### What it does
- Reads environment variables (`FP_GRPC_PORT`, `FP_AGENT_TYPE`, `LND_HOST`, `LND_PORT`, `LEDGER_DB_PATH`)
- Opens the SQLite ledger
- Starts a bare gRPC server on the configured port
- **Does NOT register any gRPC services** — the server accepts connections but has no handlers

### What's missing
- No gRPC service registration (no `RegisterXxxServer()` calls)
- Dead imports: `context`, `crypto/sha256`, `encoding/hex` are imported but unused
- No LND client connection
- No L402 interceptor
- `FinancialPodServer` struct exists but has no methods

---

## 4. Financial Pod Full Implementation (gatekeeper/) — ❌ DOES NOT COMPILE

### 4a. Main Entrypoint (gatekeeper/main.go) — 62 lines

**What it does**: CLI entrypoint with `--init` mode (generates keypairs, saves config) and runtime mode (loads config, starts Financial Pod).
**How**: Uses `flag` package, `zap` logger, `context.WithCancel`, signal handling for graceful shutdown.

### 4b. Financial Pod Core (gatekeeper/financial/financial_pod.go) — 295 lines

**What it does**: The most feature-complete file in the entire codebase. Contains:

1. **L402 gRPC Interceptor** (lines 100-132): Checks incoming gRPC calls for a `macaroon` metadata header. If missing/invalid → generates a hold invoice + macaroon and returns HTTP 402 via gRPC `PermissionDenied` status with `PaymentRequired` details.

2. **Invoice + Macaroon Generation** (lines 133-166): Creates a HODL invoice via LND, bakes a macaroon bound to the payment hash with time + account caveats, caches the invoice, logs to ledger.

3. **CallService RPC** (lines 167-178): Stub that echoes input data back (placeholder for actual agent compute dispatch).

4. **PayInvoice RPC** (lines 179-211): Client-side payment flow — checks budget, pays invoice via LND, records spend, logs to ledger.

5. **GetBudgetInfo RPC** (lines 212-225): Returns daily/monthly spend vs limits.

6. **GetChannelInfo RPC** (lines 226-247): Queries LND for active channels.

7. **Background Tasks** (lines 248-263): Periodic ticker that cleans expired invoices and re-publishes service announcements to Nostr.

8. **Service Announcement** (lines 264-279): Publishes `kind:31990` Nostr events with service name, price, and kind tags.

9. **Graceful Shutdown** (lines 280-291): Stops gRPC server, closes ledger, closes Nostr client.

### 4c. LND Client (gatekeeper/lnd/client.go) — 71 lines

**What it does**: gRPC client to connect to an LND node.
**Methods**: `Connect()`, `CreateHoldInvoice()`, `PayInvoice()`, `GetChannels()`, `Close()`

**Critical bugs**:
- Uses `grpc.WithInsecure()` — no TLS, no macaroon auth. Would fail against any real LND node.
- `CreateHoldInvoice()` uses `lnrpc.AddInvoice` with `IsHodl: true` — but `IsHodl` is NOT a real field. Real HODL invoices require `invoicesrpc.AddHoldInvoice`.

### 4d. Macaroon Manager (gatekeeper/macaroon/manager.go) — 40 lines

**What it does**: Creates and verifies macaroon tokens using `gopkg.in/macaroon.v2`.
**Create**: Bakes a macaroon with root secret, payment hash as ID, adds first-party caveats (`time < X`, `account = Y`).
**Verify**: Unmarshals and verifies HMAC signature.

**Bug**: `Verify()` checks the HMAC chain but does NOT evaluate caveat predicates. A macaroon with `time < 1000000` would pass verification even after expiry.

### 4e. Budget Manager (gatekeeper/financial/budget_manager.go) — 66 lines

**What it does**: In-memory daily/monthly spend tracking with limits.
**Bug**: `GetAvailable()` at line 62 computes `uint64 - uint64` and compares `< 0`, which is always false for unsigned integers (underflow wraps to max uint64).

### 4f. Invoice Cache (gatekeeper/financial/invoice_cache.go) — 52 lines

**What it does**: Thread-safe `map[string]*CachedInvoice` with TTL-based expiry cleanup.
**Bug**: Imports `gopkg.in/macaroon.v2` but never uses it.

### 4g. Nostr Client (gatekeeper/nostr/client.go) — 62 lines

**What it does**: Connects to Nostr relays via `go-nostr` library. Can publish events.
**Missing**: Cannot subscribe/query events. `Start()` is a no-op. No NIP-44 encryption.

### 4h. Config (gatekeeper/config/config.go) — 122 lines

**What it does**: Generates Nostr secp256k1 keypair, saves YAML config and keys to `~/.kuberbolt/<agent>/`.
**Bug**: `NostrNPub` encoding is incorrect — does `fmt.Sprintf("npub1%x", ...)` instead of proper bech32 encoding.

### 4i. Alternate Ledger (gatekeeper/ledger/ledger.go) — 85 lines

**What it does**: Event-log style ledger using `github.com/mattn/go-sqlite3` (requires CGO — fails on Windows).
**Schema**: `financial_events` (event_type, timestamp, peer, amount, payment_hash, status) + `budget_tracking`.
**Incompatible** with `fp/ledger/db.go` — different schema, different API.

---

## 5. Lightning Node P2P Setup (kuberbolt/lightning node/) — ✅ WORKING

### 5a. Docker Compose (docker-compose.yml) — 80 lines

3-container setup: `bitcoind` (regtest, lncm/bitcoind:v26.0), `lnd1` (Alice), `lnd2` (Bob).
Clean port mapping: gRPC 10009/10010, REST 8080/8081, P2P 9735/9736. No collisions.
Uses `--noseedbackup` for automatic wallet creation.

### 5b. Go Automation (main.go) — 157 lines

Automated setup script that:
1. Waits for all Docker containers to be ready
2. Creates bitcoind wallet and mines 106 blocks
3. Waits for LND nodes to sync to chain
4. Fetches pubkeys and macaroon hex from both nodes
5. Saves credentials to `test-data.json`
6. Funds User 1 wallet from bitcoind
7. Connects peers and opens a channel
8. Mines confirmation blocks
9. Verifies channel is active

### 5c. Payment with Guardrail (pay.go) — 62 lines

Decodes a BOLT11 invoice, checks amount against configurable `max_payment_sats` limit (default 1000 sats), blocks if exceeded, pays if within limit.

### 5d. Docker Exec Helpers (docker/client.go) — 120 lines

Go helper functions: `RunCmd()`, `ExecBitcoin()`, `ExecLND()`, `WaitServices()`, `GetMacaroonHex()`, `DecodeInvoice()`, `PayInvoiceWithGuardrail()`.

### 5e. Config Types (config/types.go) — 30 lines

Structs: `NodeConfig`, `ChannelParams`, `GuardrailParams`, `TestData` — JSON-serializable.

### 5f. Shell Scripts

- `auto-open-channel.sh` (55 lines): Automated connect → openchannel → mine → wait-for-active
- `peer-setup.sh` (51 lines): Manual copy-paste guide
- `backup_lnd_creds.sh` (61 lines): Export + AES-256-CBC encrypt tls.cert, admin.macaroon, graph.db
- `restore_lnd_creds.sh` (45 lines): Decrypt + docker cp back into container

---

## 6. Proto Definitions (proto/kuberbolt.proto) — ✅ CORRECT BUT UNUSED

**File**: `mock_work/proto/kuberbolt.proto` (151 lines)

Defines two gRPC services:
- **CommonSDKService**: DiscoverProviders, RequestQuote, GetHoldInvoice, PublishJobRequest, ExecuteJob, RevealPreimage, GetTransactionStatus
- **FinancialPodService**: PayHoldInvoice, SettleHoldInvoice, ValidatePaymentHold, CreateHoldInvoice

No generated code exists from this proto. The `gatekeeper/pb/` folder contains generated code from the older `service.proto` (simple TaskRequest/TaskResponse) which doesn't match the SRS.

---

## 7. Python SDK Stub (sdk/main.py) — ❌ FAKE

FastAPI + gRPC skeleton. `discover_providers()` returns hardcoded mock data. gRPC servicer exists but is never registered with the server.

## 8. Python Agent Scripts (agents/) — ❌ FAKE

`client_agent.py` and `provider_agent.py` are pure `asyncio.sleep()` + `logger.info()` scripts simulating the workflow with log messages. Zero real network calls.

## 9. Python LND Demo Scripts (demo_htlc.py, demo_macaroon.py) — ⚠️ PARTIAL

`demo_macaroon.py`: Uses LND REST API to test macaroon authentication (connect without macaroon → blocked, connect with macaroon → success). Requires `requests` library and Polar.

`demo_htlc.py`: Uses `lnd-grpc-client` to demonstrate HODL invoice lifecycle between Alice and Bob. Has a TODO note about the blocking `pay_invoice` call.

## 10. Infrastructure Scripts

- `scripts/generate-mtls-certs.sh` (69 lines): Generates CA + per-component mTLS certificates
- `scripts/init-regtest.sh` (78 lines): 3-node regtest init (different from lightning node's 2-node setup)
- `polar/setup-polar-automated.sh` (109 lines): Creates Polar network config JSON for alice/bob/charlie
