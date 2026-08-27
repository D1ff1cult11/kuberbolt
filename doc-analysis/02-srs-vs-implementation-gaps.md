# SRS vs Implementation — Gap Analysis

This document maps every SRS functional and non-functional requirement to the current codebase,
showing exactly what is covered, what is partial, and what is completely missing.

---

## Functional Requirements

### FR-6.1 — Agent Registration (Identity Creation)

| Requirement | SRS Text | Status | Where Implemented | Gap |
|---|---|---|---|---|
| FR-6.1.1 | SDK must generate Nostr keypair, never expose private key beyond Frontend response | ⚠️ PARTIAL | `gatekeeper/config/config.go` generates secp256k1 keypair | Keypair gen is in Go config, not in SDK. Private key written to plaintext file (`keys.json`). NPub encoding is wrong (not bech32). |
| FR-6.1.2 | SDK must publish `kind:0` profile event | ⚠️ PARTIAL | `gatekeeper/nostr/client.go` can publish events | `PublishEvent()` exists but is only called for `kind:31990`. No dedicated `kind:0` profile publish. |
| FR-6.1.3 | SDK must publish `kind:31990` service listing | ⚠️ PARTIAL | `gatekeeper/financial/financial_pod.go` lines 264-279 | `publishServiceAnnouncement()` publishes `kind:31990` with name, price, kind tags. But runs as background task in FP, not in SDK. |
| FR-6.1.4 | Frontend must persist/display returned keypair | ❌ MISSING | — | No frontend exists. |

---

### FR-6.2 — Agent Pod Deployment

| Requirement | SRS Text | Status | Where Implemented | Gap |
|---|---|---|---|---|
| FR-6.2.1 | Frontend must accept instructions + Lightning credentials | ❌ MISSING | — | No frontend, no provisioning flow. |
| FR-6.2.2 | Pod must instantiate Agent + Ledger + FP + LN Node | ⚠️ PARTIAL | `docker-compose.yml` defines containers | Docker compose exists but doesn't provision the 4 components as a unit. Agent and FP are separate images. |
| FR-6.2.3 | Lightning Node must verify Bitcoin Layer connectivity | ⚠️ PARTIAL | `lightning node/main.go` waits for chain sync | Only in the test automation, not in the FP daemon startup. |
| FR-6.2.4 | Lightning credentials must not be accessible to Agent | ❌ MISSING | — | No credential isolation between Agent and FP processes. |

---

### FR-6.3 — Agent Discovery

| Requirement | SRS Text | Status | Where Implemented | Gap |
|---|---|---|---|---|
| FR-6.3.1 | SDK must query Nostr for `kind:31990` events by hashtag | ❌ MISSING | — | Nostr client can PUBLISH but cannot SUBSCRIBE or QUERY. No filter logic. |
| FR-6.3.2 | SDK must return candidate list to Agent | ❌ MISSING | — | SDK is a fake Python stub returning hardcoded data. |

---

### FR-6.4 — Private Endpoint Negotiation

| Requirement | SRS Text | Status | Where Implemented | Gap |
|---|---|---|---|---|
| FR-6.4.1 | Endpoint resolution must use NIP-44 encrypted DMs | ❌ MISSING | — | No NIP-44 implementation anywhere. |
| FR-6.4.2 | Resolved endpoint must go to FP, not Agent | ❌ MISSING | — | No endpoint negotiation flow exists. |

---

### FR-6.5 — Service Request & L402 Payment

| Requirement | SRS Text | Status | Where Implemented | Gap |
|---|---|---|---|---|
| FR-6.5.1 | Service FP must respond with L402 challenge (macaroon + invoice) | ⚠️ PARTIAL | `financial_pod.go` L100-166 | gRPC interceptor returns 402 with invoice + macaroon. BUT: uses wrong LND API for HODL invoices. |
| FR-6.5.2 | Invoice must be a HODL (hold) invoice | ❌ BROKEN | `lnd/client.go` L45-52 | Uses `lnrpc.AddInvoice` with fake `IsHodl` field. Real HODL invoices require `invoicesrpc.AddHoldInvoice`. |
| FR-6.5.3 | Client FP must pay invoice and retry with macaroon + preimage | ⚠️ PARTIAL | `financial_pod.go` L179-211 | `PayInvoice()` exists but doesn't handle the retry-with-preimage flow. Interceptor doesn't check for preimage on retry. |
| FR-6.5.4 | Service FP must verify macaroon validity + preimage matches hash | ⚠️ PARTIAL | `macaroon/manager.go` | HMAC verification exists but caveat predicates (time, account) are NOT checked. Preimage-to-hash verification is not implemented. |
| FR-6.5.5 | Service FP must settle HODL only after successful compute | ❌ MISSING | — | No settlement logic. `CallService()` is a stub that echoes input. No compute → settle flow. |
| FR-6.5.6 | Both FPs must record transaction in SQLite Ledger | ⚠️ PARTIAL | `financial_pod.go` L123-155, L200-206 | Logs events but uses wrong ledger (CGO-dependent `mattn/go-sqlite3`). Schema doesn't match SRS §8. |

---

### FR-6.6 — Output Return & Review

| Requirement | SRS Text | Status | Where Implemented | Gap |
|---|---|---|---|---|
| FR-6.6.1 | Service FP must return output only after settlement | ❌ MISSING | — | No settlement-gated output return. |
| FR-6.6.2 | Client FP must forward output to its Agent for review | ❌ MISSING | — | No FP → Agent output forwarding. |

---

### FR-6.7 — Feedback Publishing

| Requirement | SRS Text | Status | Where Implemented | Gap |
|---|---|---|---|---|
| FR-6.7.1 | Agent must submit feedback through SDK | ❌ MISSING | — | No feedback submission API. |
| FR-6.7.2 | SDK must publish `kind:7000` feedback event | ❌ MISSING | — | No kind:7000 support anywhere. |

---

## Non-Functional Requirements

| Requirement | SRS Text | Status | Gap |
|---|---|---|---|
| NFR-1 (Key isolation) | Private keys handled only by SDK + FP, never by Agent, never logged in plaintext | ❌ MISSING | Private key written to plaintext `keys.json`. No isolation between Agent and FP. |
| NFR-2 (Non-custodial) | Only pod's own LN Node holds/moves funds. HODL enforces compute-first | ❌ BROKEN | HODL invoices use wrong API. No settlement-after-compute flow. |
| NFR-3 (Metadata privacy) | Endpoints travel only through NIP-44 | ❌ MISSING | No NIP-44 implementation. |
| NFR-4 (Idempotency) | Retried requests must not cause duplicate invoices/compute | ❌ MISSING | No deduplication logic. |
| NFR-5 (Auditability) | Every payment event in SQLite Ledger | ⚠️ PARTIAL | Ledger exists but schema doesn't match SRS §8. Two incompatible ledger implementations. |
| NFR-6 (Multi-relay) | SDK must support multiple relays | ⚠️ PARTIAL | Nostr client accepts relay list, iterates on publish. But no subscribe/query. |
| NFR-7 (Timeout handling) | Auto-cancel unsettled HODL invoices after timeout | ❌ MISSING | Invoice cache has TTL expiry but no LND cancel-invoice call. |

---

## Summary Scorecard

| Category | Total Requirements | ✅ Implemented | ⚠️ Partial | ❌ Missing/Broken |
|---|---|---|---|---|
| FR-6.1 Registration | 4 | 0 | 3 | 1 |
| FR-6.2 Deployment | 4 | 0 | 2 | 2 |
| FR-6.3 Discovery | 2 | 0 | 0 | 2 |
| FR-6.4 Endpoint Negotiation | 2 | 0 | 0 | 2 |
| FR-6.5 L402 Payment | 6 | 0 | 4 | 2 |
| FR-6.6 Output Return | 2 | 0 | 0 | 2 |
| FR-6.7 Feedback | 2 | 0 | 0 | 2 |
| NFR (Non-functional) | 7 | 0 | 2 | 5 |
| **TOTAL** | **29** | **0** | **11** | **18** |

**Zero requirements are fully implemented.** 11 are partially addressed (scaffolding exists but with bugs or incomplete logic). 18 are completely missing.

---

## Data Model Gap (SRS §8 vs Current Ledger)

| SRS §8 Field | fp/ledger/db.go | gatekeeper/ledger/ledger.go |
|---|---|---|
| `job_id` | Only in `payment_holds`, not in main ledger | ❌ Missing |
| `counterparty_pubkey` | ❌ Missing (has `agent_pubkey` but no counterparty) | Has `peer` (partial) |
| `direction` | ✅ Present | ❌ Missing (uses `event_type` instead) |
| `amount_sats` | Has `amount_msat` (close enough) | Has `amount` (no unit specified) |
| `invoice_payment_hash` | Has `hold_invoice_hash` | Has `payment_hash` |
| `macaroon_id` | ❌ Missing | ❌ Missing |
| `status` | ✅ Present | ✅ Present |
| `created_at` / `settled_at` | ✅ Present | Has `timestamp` only (no settled_at) |
