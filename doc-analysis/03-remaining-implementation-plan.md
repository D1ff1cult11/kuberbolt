# Remaining Implementation — Full Build Plan

This document details everything that must be built to achieve a fully SRS-compliant system,
organized by component and phase.

---

## Phase 1: Foundation — Make It Compile & Connect to LND

### 1.1 Unified Financial Pod Go Module

**Goal**: One Go module (`agent-pod/financial-pod/`) that compiles cleanly on Windows and connects to a real LND node.

#### 1.1.1 Fix `go.mod`
- Module path: `github.com/kuberbolt/financial-pod`
- Use `modernc.org/sqlite` (pure Go, no CGO)
- Pin LND dependencies correctly:
  - `github.com/lightningnetwork/lnd` → latest stable tag
  - `google.golang.org/grpc` → compatible version
  - `gopkg.in/macaroon.v2`
  - `go.uber.org/zap`
  - `github.com/nbd-wtf/go-nostr` (maintained fork of go-nostr)
- Add `replace` directives for any protobuf conflicts

#### 1.1.2 Fix LND Client (`internal/ln/client.go`)
Current code uses `grpc.WithInsecure()` and fake `IsHodl` field. Must:

1. **TLS Authentication**: Read `tls.cert` from disk, create `credentials.NewClientTLSFromFile()`
2. **Macaroon Authentication**: Read `admin.macaroon` from disk, hex-encode, inject via `metadata.AppendToOutgoingContext()`
3. **Hold Invoice API**: Replace `lnrpc.AddInvoice` with `invoicesrpc.AddHoldInvoice`:
   ```go
   // Correct way to create a hold invoice
   invoicesClient := invoicesrpc.NewInvoicesClient(conn)
   resp, err := invoicesClient.AddHoldInvoice(ctx, &invoicesrpc.AddHoldInvoiceRequest{
       Hash:      rhash,       // SHA256 of preimage
       ValueMsat: amountMSat,
       Expiry:    int64(timeoutSeconds),
   })
   ```
4. **Settle Invoice**: Add `invoicesClient.SettleInvoice(ctx, &invoicesrpc.SettleInvoiceMsg{Preimage: preimage})`
5. **Cancel Invoice**: Add `invoicesClient.CancelInvoice(ctx, &invoicesrpc.CancelInvoiceMsg{PaymentHash: hash})`
6. **Subscribe to Invoice State**: Add `invoicesClient.SubscribeSingleInvoice()` for real-time HTLC state tracking

#### 1.1.3 Fix Macaroon Manager (`internal/l402/macaroon.go`)
Current `Verify()` doesn't check caveat predicates. Must:

1. **Parse caveats**: Extract `time < X` and `account = Y` from the macaroon's first-party caveats
2. **Time check**: Compare `time < X` against `time.Now().Unix()`
3. **Account binding**: Verify `account = Y` matches the payment hash of the current request
4. **Preimage verification**: Add `VerifyWithPreimage(macBytes, preimage)` that checks `SHA256(preimage) == paymentHash`

#### 1.1.4 Fix Budget Manager (`internal/budget/manager.go`)
- Fix unsigned integer underflow at `GetAvailable()`: cast to `int64` before subtraction, or use `if dailySpent >= limit { return 0 }`
- Add persistence: load daily/monthly spend from ledger on startup instead of starting at 0

#### 1.1.5 Align Ledger Schema to SRS §8
Add missing columns to `fp/ledger/db.go`:
```sql
ALTER TABLE ledger ADD COLUMN job_id TEXT;
ALTER TABLE ledger ADD COLUMN counterparty_pubkey TEXT;
ALTER TABLE ledger ADD COLUMN macaroon_id TEXT;
```
Or recreate with the complete schema:
```sql
CREATE TABLE IF NOT EXISTS ledger (
    job_id TEXT PRIMARY KEY,
    counterparty_pubkey TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('incoming', 'outgoing')),
    amount_msat INTEGER NOT NULL,
    invoice_payment_hash TEXT NOT NULL,
    macaroon_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'settled', 'cancelled', 'expired')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    settled_at DATETIME
);
```

#### 1.1.6 Generate Proto Code
Run `protoc` on `kuberbolt.proto` to generate Go stubs:
```bash
protoc --go_out=. --go-grpc_out=. proto/agent_service.proto
```
Register both `ExecutionServiceServer` and `FinancialPodServiceServer` in `main.go`.

**Verification**: `go build ./...` succeeds. `go run cmd/financialpod/main.go --init --name test-agent` creates config. Connect to Polar/Docker LND node and call `GetInfo`.

---

### 1.2 Lightning Infrastructure Verification

The `lightning node/` setup is already working. Verify it still works after migration:
```bash
cd lightning-infra
docker compose -f docker-compose.lnd.yml up -d
go run main.go  # automated setup
```

---

## Phase 2: Core L402 Payment Flow (SRS §6.5)

### 2.1 Service-Side Flow (Provider FP)

1. **Receive unauthenticated request** → L402 interceptor fires
2. **Generate preimage** (32 random bytes) and compute `rhash = SHA256(preimage)`
3. **Create HODL invoice** via `invoicesrpc.AddHoldInvoice(hash=rhash, value_msat=price)`
4. **Bake macaroon** bound to `rhash` with time caveat
5. **Return 402** with invoice + macaroon in gRPC status details
6. **Store** preimage → rhash → job_id mapping in ledger
7. **Wait for payment**: Subscribe to invoice state via `SubscribeSingleInvoice(rhash)`
8. **On ACCEPTED state** (HTLC locked): Mark job as "funded"

### 2.2 Client-Side Flow (Client FP)

1. **Send request** → receive 402 response with invoice + macaroon
2. **Check budget** via BudgetManager
3. **Pay invoice** via `lnrpc.SendPaymentSync(paymentRequest)`
4. **Extract preimage** from payment response
5. **Retry request** with `macaroon` + `preimage` in gRPC metadata
6. **Receive result** and forward to Agent

### 2.3 Settlement Flow (Provider FP continued)

1. **Receive retry** with macaroon + preimage
2. **Verify macaroon** HMAC chain + caveats
3. **Verify preimage** matches rhash: `SHA256(preimage) == stored_rhash`
4. **Dispatch to Agent** for compute
5. **On success**: `invoicesClient.SettleInvoice(preimage)` → funds disbursed
6. **On failure/timeout**: `invoicesClient.CancelInvoice(paymentHash)` → funds released
7. **Return output** to client FP
8. **Log** transaction in both ledgers

### 2.4 Integration Test

Write a Go test that:
- Starts two FP instances (client + provider) against two Polar/Docker LND nodes
- Client calls Provider → gets 402 → pays → retries → gets result → HODL settles
- Assert both ledger databases have correct records
- Assert LND channel balances changed correctly

**Verification**: Integration test passes. Channel balances update. Both `ledger.db` files show matching records.

---

## Phase 3: Nostr SDK (SRS §6.1, §6.3, §6.4, §6.7)

### 3.1 Python SDK Package (`sdk/python/nostr_sdk_wrapper/`)

#### 3.1.1 `identity.py`
- Generate Nostr keypair (secp256k1)
- Encode as `nsec`/`npub` (bech32)
- Return keypair to caller
- Use `nostr-sdk` Python library (Rust bindings, well-maintained)

#### 3.1.2 `profile.py`
- Build `kind:0` event with `{"name": "...", "about": "...", "picture": "..."}`
- Sign with private key
- Publish to configured relay list

#### 3.1.3 `listing.py`
- Build `kind:31990` event (NIP-89 replaceable) with:
  - Content: service description JSON
  - Tags: `["d", agent_name]`, `["k", kind_number]`, `["price", amount_msat]`
- Sign and publish

#### 3.1.4 `discovery.py`
- Subscribe to relays with filter: `kinds=[31990]`, `#t=[hashtag]`
- Parse returned events into `ProviderInfo` objects
- Return candidate list

#### 3.1.5 `dm.py`
- Implement NIP-44 encryption (XChaCha20-Poly1305)
- Send encrypted DM containing service endpoint URL
- Receive and decrypt endpoint from response
- Deliver endpoint to Financial Pod (not Agent)

#### 3.1.6 `feedback.py`
- Build `kind:7000` event referencing job ID and counterparty pubkey
- Include rating and optional text feedback
- Sign and publish

### 3.2 Nostr Relay for Local Dev
Add `nostr-rs-relay` container to `lightning-infra/docker-compose.lnd.yml`:
```yaml
relay:
  image: scsibug/nostr-rs-relay:latest
  ports:
    - "8008:8080"
  volumes:
    - relay_data:/data
```

**Verification**: Two agents register on local relay, discover each other via `kind:31990` query, exchange endpoints via NIP-44 DM.

---

## Phase 4: Agent Pod (Brain + FP together)

### 4.1 Python Brain (`agent-pod/brain/`)

#### 4.1.1 `financial_pod_client.py`
gRPC client to call the local Financial Pod daemon:
- `pay_hold_invoice(invoice)` → triggers payment
- `get_budget_info()` → returns spend/limits
- `get_channel_info()` → returns LN channel state

#### 4.1.2 `langchain_agent.py`
LangChain agent with custom tools:
- `DiscoverProviders(kind, filters)` → calls SDK discovery
- `RequestService(provider_pubkey, job_spec)` → calls FP which handles L402 automatically
- `SubmitFeedback(job_id, rating)` → calls SDK feedback

#### 4.1.3 `docker-compose.pod.yml`
Single-machine compose for brain + FP:
```yaml
services:
  brain:
    build: ./brain
    environment:
      FP_GRPC_HOST: financial-pod
      FP_GRPC_PORT: 6001
  financial-pod:
    build: ./financial-pod
    environment:
      LND_HOST: <remote-lnd-host>
      LND_GRPC_PORT: 10009
    ports:
      - "6001:6001"
```

**Verification**: Agent registers identity, discovers providers, requests service (L402 flow), receives output, posts feedback. Full lifecycle.

---

## Phase 5: End-to-End & Polish

### 5.1 `e2e-test.sh`
Automated script that:
1. Starts lightning-infra (bitcoind + 2 LND nodes)
2. Starts Nostr relay
3. Deploys 2 agent pods (client + provider)
4. Client registers → discovers provider → requests service → pays → gets result → posts feedback
5. Asserts: both ledgers correct, channel balances correct, feedback event on relay

### 5.2 Frontend (Next.js)
- Registration form: username, services, price
- Calls SDK for keypair generation
- Displays keys securely
- Deployment form: instructions + Lightning credentials

### 5.3 NFR Compliance
- NFR-1: Move key storage to encrypted keystore, never log in plaintext
- NFR-4: Add idempotency keys to request/invoice pairs (dedup by job_id)
- NFR-7: Background goroutine that auto-cancels HODL invoices past timeout

### 5.4 CI/CD
- `.github/workflows/ci-go.yml`: `go build`, `go test`, `go vet`
- `.github/workflows/ci-python.yml`: `pytest`, `ruff`, `mypy`

---

## Implementation Order Summary

```
Phase 1 (Foundation)         ~3 days
├── Fix go.mod + dependencies
├── Fix LND client (TLS, macaroon, HODL API)
├── Fix macaroon verifier (caveats)
├── Fix budget manager (underflow)
├── Align ledger schema to SRS §8
├── Generate proto code
└── Verify LND connection against Docker/Polar

Phase 2 (L402 Flow)          ~4 days
├── Service-side L402 flow (HODL create → settle)
├── Client-side L402 flow (pay → retry → receive)
├── Integration test (2 FPs + 2 LND nodes)
└── Ledger verification

Phase 3 (Nostr SDK)           ~3 days
├── Python SDK: identity, profile, listing
├── Python SDK: discovery, DM (NIP-44), feedback
├── Add Nostr relay to docker-compose
└── Discovery integration test

Phase 4 (Agent Pod)           ~2 days
├── Python brain with LangChain
├── FP gRPC client
├── Pod docker-compose
└── Full lifecycle test

Phase 5 (E2E & Polish)       ~3 days
├── E2E test script
├── Frontend (Next.js)
├── NFR compliance
└── CI/CD
```

**Total estimated: ~15 working days for a complete, SRS-compliant system.**
