# Open Source Contribution Workflow: Phase 1 & Phase 2

To simulate a professional 2-person open-source workflow, we have broken down the recent work into 4 distinct GitHub Issues. Each issue includes a detailed description, suggested branch names, and best-practice commit messages.

---

## Issue #1: Foundation & Core Modules Restructuring
**Assignee:** Contributor A
**Labels:** `enhancement`, `architecture`
**Suggested Branch:** `feature/core-modules-init`

### Issue Description (For GitHub)
```markdown
**Is your feature request related to a problem? Please describe.**
The legacy architecture suffers from tight coupling and a disorganized directory structure. We need to migrate the codebase to the canonical `github.com/kuberbolt/financial-pod` module path and build independent, testable foundational modules (ledger, cache, config).

**Describe the solution you'd like**
1. Initialize a new `go.mod` with the correct module path.
2. Resolve LND dependencies (including the `protobuf-go-hex-display` replace directive for v0.18.5-beta).
3. Implement `internal/config` to safely load LND paths.
4. Implement a pure Go SQLite database in `internal/ledger` using `modernc.org/sqlite` to avoid CGO dependencies.
5. Create the HODL invoice cache in `internal/cache`.
6. Add the CLI entrypoint in `cmd/financialpod/main.go` with signal handling.

**Acceptance Criteria**
- Code compiles (`go build ./...`).
- Dependencies correctly resolved via `go mod tidy`.
- SQLite database initializes properly.
```

### Commit History
1. `chore: initialize go.mod with lnd dependencies and replace directives`
2. `feat(config): implement yaml config loader for lightning credentials`
3. `feat(ledger): implement pure go sqlite database adhering to srs schema`
4. `feat(cache): implement thread-safe hodl invoice cache`
5. `feat(cmd): add main entrypoint with graceful shutdown and init flag`

---

## Issue #2: Lightning Network Client & Budget Manager
**Assignee:** Contributor B
**Labels:** `enhancement`, `lnd`
**Suggested Branch:** `feature/lnd-client-budget`

### Issue Description (For GitHub)
```markdown
**Is your feature request related to a problem? Please describe.**
The Financial Pod needs to communicate securely with a local LND node using TLS certificates and Macaroons. Furthermore, our previous budget manager suffered from `uint64` underflow bugs which could cause panics.

**Describe the solution you'd like**
1. Create `internal/ln/client.go` to handle gRPC connections to LND.
2. Implement methods for HODL invoices: `AddHoldInvoice`, `SettleInvoice`, `CancelInvoice`, and a streaming `SubscribeSingleInvoice`.
3. Re-write `internal/budget/manager.go` using safe `int64` arithmetic to track spending securely.
4. Connect the budget manager to the SQLite ledger for persistence.

**Acceptance Criteria**
- LND client successfully connects using provided cert/macaroon.
- Budget manager rejects spending limits when insufficient funds exist.
- No `uint64` underflows.
```

### Commit History
1. `feat(ln): implement grpc client with tls and macaroon authentication`
2. `feat(ln): add hodl invoice lifecycle methods and streaming subscriptions`
3. `fix(budget): resolve uint64 underflow vulnerability by enforcing int64 arithmetic`
4. `feat(budget): integrate budget manager with persistent sqlite ledger`
5. `test(budget): add unit tests for spending limit enforcement`

---

## Issue #3: L402 Macaroon Bakery Implementation
**Assignee:** Contributor A
**Labels:** `enhancement`, `security`
**Suggested Branch:** `feature/l402-macaroon-bakery`

### Issue Description (For GitHub)
```markdown
**Is your feature request related to a problem? Please describe.**
To support the L402 protocol, the Financial Pod must act as a Macaroon Bakery. It needs to issue macaroons tied to specific lightning payment hashes and enforce expiration limits.

**Describe the solution you'd like**
1. Implement `internal/l402/macaroon.go` using `gopkg.in/macaroon.v2`.
2. Create `CreateMacaroon(paymentHash, ttl)` which adds two first-party caveats: `time < X` and `account = <hash>`.
3. Create `VerifyWithPreimage(macaroon, preimage)` which validates the HMAC chain, ensures the macaroon is not expired, and confirms `SHA256(preimage) == account_hash`.

**Acceptance Criteria**
- Macaroons can be baked and serialized.
- Verification fails if the macaroon is expired.
- Verification fails if the preimage does not hash to the account caveat.
```

### Commit History
1. `feat(l402): implement macaroon bakery using gopkg.in/macaroon.v2`
2. `feat(l402): add time expiration and account payment hash caveats`
3. `feat(l402): implement VerifyWithPreimage to cryptographically bind invoices`
4. `test(l402): add unit tests for caveat verification and expiration`

---

## Issue #4: Gateway Interceptors & L402 State Machine
**Assignee:** Contributor B
**Labels:** `enhancement`, `core-flow`
**Suggested Branch:** `feature/gateway-l402-flow`

### Issue Description (For GitHub)
```markdown
**Is your feature request related to a problem? Please describe.**
With the foundations complete, we need to wire everything together via gRPC interceptors. The gateway must intercept incoming requests (acting as the Provider) and intercept outgoing requests (acting as the Requester).

**Describe the solution you'd like**
1. Implement `internal/gateway/provider.go` to handle inbound calls. It should generate a preimage, create a HODL invoice, return `402 Payment Required`, and wait for `ACCEPTED` state before executing compute and settling.
2. Implement `internal/gateway/requester.go` to handle outbound calls. It should catch `402` errors, verify budgets, pay the HODL invoice, extract the returned preimage, and retry the request.
3. Wire both into a custom gRPC server in `internal/gateway/server.go`.
4. Build a comprehensive Docker integration test (`TestL402Integration`).

**Acceptance Criteria**
- Successful round-trip L402 HODL flow.
- Gateway correctly extracts preimage upon settlement.
- Integration tests pass against real Docker LND nodes.
```

### Commit History
1. `feat(gateway): implement provider state machine for inbound l402 requests`
2. `feat(gateway): implement requester state machine for outbound l402 payments`
3. `feat(gateway): wire interceptors into central grpc server`
4. `test(gateway): create comprehensive docker-based lnd integration test`
5. `fix(gateway): replace deprecated grpc.WithInsecure with insecure.NewCredentials`
