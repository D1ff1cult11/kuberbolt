# How Real LND Integration Actually Works — Deep Dive

This document explains exactly how the Financial Pod connects to a real LND node,
how every byte moves through the system, and what the actual code looks like.

---

## 1. The Physical Setup

Before any code runs, this is what exists on the machine(s):

```
Machine (or Docker host)
├── bitcoind container          ← Bitcoin Core in regtest mode
│   └── Blockchain data         ← Holds the actual Bitcoin ledger
│
├── LND container               ← Lightning Network Daemon
│   └── /root/.lnd/
│       ├── tls.cert             ← TLS certificate (public)
│       ├── tls.key              ← TLS private key (LND keeps this)
│       └── data/chain/bitcoin/regtest/
│           └── admin.macaroon   ← Auth token (like an API key)
│
└── Financial Pod (your Go binary)
    ├── Reads tls.cert           ← To verify LND's identity
    ├── Reads admin.macaroon     ← To prove we're authorized
    └── Connects to LND:10009    ← gRPC over TLS
```

**Key insight**: LND exposes a gRPC API on port 10009. To call it, you need TWO things:
1. The `tls.cert` file — proves you're talking to the real LND (not a man-in-the-middle)
2. The `admin.macaroon` file — proves you're authorized to call admin RPCs

Without both, LND refuses your connection.

---

## 2. Step-by-Step: Connecting to LND (The Real Way)

### Step 2a: Read the TLS Certificate

```go
// Read LND's TLS certificate from disk
tlsCert, err := os.ReadFile("/path/to/tls.cert")
if err != nil {
    log.Fatalf("Cannot read TLS cert: %v", err)
}

// Create a certificate pool and add LND's cert
certPool := x509.NewCertPool()
if !certPool.AppendCertsFromPEM(tlsCert) {
    log.Fatal("Failed to parse TLS cert")
}

// Create TLS credentials that trust only this specific certificate
tlsCreds := credentials.NewClientTLSFromCert(certPool, "")
```

**What's happening**: LND generates a self-signed TLS certificate when it starts. Since it's self-signed, your OS doesn't trust it by default. By loading the cert file manually, you're telling Go: "I trust this specific certificate."

### Step 2b: Read the Macaroon

```go
// Read the binary macaroon file
macBytes, err := os.ReadFile("/path/to/admin.macaroon")
if err != nil {
    log.Fatalf("Cannot read macaroon: %v", err)
}

// Hex-encode it (LND expects this format in gRPC metadata)
macHex := hex.EncodeToString(macBytes)
```

**What's happening**: A macaroon is a binary token (like a cookie). LND checks it on every RPC call. The `admin.macaroon` has full permissions. There are also `readonly.macaroon` and `invoice.macaroon` with limited permissions.

### Step 2c: Create a gRPC Connection with Both

```go
// Create a "per-RPC credential" that attaches the macaroon to every call
macaroonCred := NewMacaroonCredential(macHex)

// Dial LND with TLS + macaroon
conn, err := grpc.Dial(
    "localhost:10009",
    grpc.WithTransportCredentials(tlsCreds),     // TLS layer
    grpc.WithPerRPCCredentials(macaroonCred),    // Macaroon on every call
)
```

The macaroon credential implements gRPC's `PerRPCCredentials` interface:

```go
type MacaroonCredential struct {
    MacaroonHex string
}

// GetRequestMetadata is called automatically before every gRPC call
func (m *MacaroonCredential) GetRequestMetadata(ctx context.Context, uri ...string) (map[string]string, error) {
    return map[string]string{
        "macaroon": m.MacaroonHex,  // LND reads this header
    }, nil
}

// RequireTransportSecurity tells gRPC: "only send this over TLS"
func (m *MacaroonCredential) RequireTransportSecurity() bool {
    return true
}
```

**What's happening on the wire**:
```
Your Go binary                          LND (port 10009)
     │                                       │
     │──── TLS Handshake ──────────────────►│
     │     (presents tls.cert for verify)    │
     │◄─── TLS Established ────────────────│
     │                                       │
     │──── gRPC Call: GetInfo ────────────►│
     │     Header: macaroon=0201036c6e64...  │
     │                                       │
     │     LND checks:                       │
     │     1. Is TLS valid? ✓                │
     │     2. Is macaroon valid? ✓           │
     │     3. Does macaroon have perms? ✓    │
     │                                       │
     │◄─── Response: {identity_pubkey: ...} │
```

### Step 2d: Create RPC Clients

```go
// Standard Lightning RPC client (invoices, payments, channels)
lnClient := lnrpc.NewLightningClient(conn)

// Invoices RPC client (HODL invoices specifically)
invoicesClient := invoicesrpc.NewInvoicesClient(conn)

// Router RPC client (payment tracking)
routerClient := routerrpc.NewRouterClient(conn)
```

**Why three clients?** LND splits its API into sub-services. Regular invoices use `lnrpc`, but HODL invoices use `invoicesrpc` (a separate protobuf service). This is exactly where the current `gatekeeper/lnd/client.go` fails — it uses `lnrpc.AddInvoice` instead of `invoicesrpc.AddHoldInvoice`.

---

## 3. The Complete L402 Payment Flow — What Actually Happens

Here's every single step with the actual LND API calls:

### Phase A: Client Agent Wants to Buy Compute

```
Client Agent (Python)           Client Financial Pod (Go)
     │                                    │
     │── "Run YOLOv9 on this image" ────►│
     │                                    │
     │   FP knows Provider's gRPC        │
     │   endpoint from Nostr DM          │
     │                                    │
```

### Phase B: Client FP Calls Provider FP — Gets 402

```
Client FP                               Provider FP
     │                                        │
     │── gRPC: CallService(job_spec) ───────►│
     │   (no macaroon header)                 │
     │                                        │
     │   Provider's L402 Interceptor fires:   │
     │   1. Check metadata for "macaroon" key │
     │   2. Not found → generate challenge    │
     │                                        │
```

**Inside the Provider FP's L402 Interceptor** (this is the actual code flow):

```go
func L402Interceptor(ctx context.Context, req interface{}, 
    info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (interface{}, error) {
    
    // 1. Extract metadata from the incoming gRPC call
    md, ok := metadata.FromIncomingContext(ctx)
    if !ok {
        // No metadata at all → must challenge
        return nil, issueL402Challenge(ctx)
    }
    
    // 2. Check for macaroon header
    macValues := md.Get("macaroon")
    if len(macValues) == 0 {
        // No macaroon → must challenge
        return nil, issueL402Challenge(ctx)
    }
    
    // 3. Check for preimage header (proves payment was made)
    preimageValues := md.Get("preimage")
    if len(preimageValues) == 0 {
        // Has macaroon but no preimage → payment not made yet
        return nil, status.Error(codes.PermissionDenied, "preimage required")
    }
    
    // 4. Verify macaroon signature + caveats
    if !verifyMacaroon(macValues[0]) {
        return nil, status.Error(codes.PermissionDenied, "invalid macaroon")
    }
    
    // 5. Verify preimage matches the payment hash in the macaroon
    if !verifyPreimage(preimageValues[0], macValues[0]) {
        return nil, status.Error(codes.PermissionDenied, "preimage mismatch")
    }
    
    // 6. All checks passed → forward to actual handler
    return handler(ctx, req)
}
```

### Phase C: Provider FP Creates HODL Invoice

This is the critical difference between a normal invoice and a HODL invoice:

**Normal Invoice:**
```
Create Invoice → Client Pays → Funds IMMEDIATELY go to Provider
(Provider has no control over timing)
```

**HODL Invoice:**
```
Create Invoice → Client Pays → Funds LOCKED in HTLC
                                      │
                              Provider decides:
                              ├── Reveal preimage → Funds SETTLE to Provider
                              └── Don't reveal   → Funds RETURN to Client (after timeout)
```

**Actual LND API calls:**

```go
func (fp *FinancialPod) issueL402Challenge(ctx context.Context) error {
    // 1. Generate a random 32-byte preimage (the "secret")
    preimage := make([]byte, 32)
    crypto_rand.Read(preimage)
    
    // 2. Compute the SHA256 hash of the preimage (the "lock")
    hash := sha256.Sum256(preimage)
    
    // 3. Create a HODL invoice on LND
    //    THIS IS THE CORRECT API — not lnrpc.AddInvoice
    holdInvoiceResp, err := fp.invoicesClient.AddHoldInvoice(ctx, 
        &invoicesrpc.AddHoldInvoiceRequest{
            Hash:   hash[:],           // The SHA256 hash (32 bytes)
            Value:  50,                // 50 satoshis
            Expiry: 3600,              // Invoice expires in 1 hour
            Memo:   "Kuberbolt: YOLOv9 inference",
        },
    )
    // holdInvoiceResp.PaymentRequest = "lnbcrt500n1pj..." (BOLT11 string)
    
    // 4. Store the preimage in our database
    //    ONLY the provider knows the preimage at this point
    fp.ledger.RecordPaymentHold(&ledger.PaymentHold{
        RHash:    hex.EncodeToString(hash[:]),
        Preimage: hex.EncodeToString(preimage),
        JobID:    generateJobID(),
    })
    
    // 5. Bake a macaroon bound to this payment hash
    mac, _ := macaroon.New(
        fp.rootKey,                              // Root signing key
        hash[:],                                 // ID = payment hash
        "kuberbolt",                             // Location
        macaroon.LatestVersion,
    )
    mac.AddFirstPartyCaveat([]byte(
        fmt.Sprintf("expires_at = %d", time.Now().Add(2*time.Hour).Unix()),
    ))
    macBytes, _ := mac.MarshalBinary()
    
    // 6. Return 402 with invoice + macaroon in gRPC status details
    st := status.New(codes.PermissionDenied, "Payment Required")
    st, _ = st.WithDetails(&lnrpc.PayReqString{
        PayReq: holdInvoiceResp.PaymentRequest,
    })
    // Also attach macaroon in response metadata
    grpc.SetHeader(ctx, metadata.Pairs(
        "www-authenticate", fmt.Sprintf("L402 macaroon=%s, invoice=%s",
            hex.EncodeToString(macBytes),
            holdInvoiceResp.PaymentRequest,
        ),
    ))
    
    return st.Err()
}
```

**What's happening on LND's side when `AddHoldInvoice` is called:**

```
Your Financial Pod                    LND Node
     │                                   │
     │── AddHoldInvoice(hash, 50sat) ──►│
     │                                   │
     │   LND stores internally:          │
     │   {                               │
     │     hash: abc123...,              │
     │     state: OPEN,                  │
     │     value: 50 sat,                │
     │     expiry: 3600s,                │
     │     // LND does NOT have the      │
     │     // preimage — only the hash   │
     │   }                               │
     │                                   │
     │◄── PaymentRequest: "lnbcrt..." ──│
     │                                   │
```

### Phase D: Client FP Pays the Invoice

```go
func (fp *ClientFinancialPod) payInvoice(paymentRequest string) ([]byte, error) {
    // 1. Budget check first
    if !fp.budget.CanSpend(50000) { // 50 sats = 50000 msat
        return nil, fmt.Errorf("budget exceeded")
    }
    
    // 2. Send payment via LND
    //    This is a SYNCHRONOUS call — it blocks until payment succeeds or fails
    payResp, err := fp.lnClient.SendPaymentSync(ctx, &lnrpc.SendRequest{
        PaymentRequest: paymentRequest,
    })
    if err != nil {
        return nil, err
    }
    
    // payResp.PaymentPreimage contains the preimage!
    // Wait — how does the client get the preimage if only the provider has it?
    // Answer: They DON'T yet. For HODL invoices, this call BLOCKS
    // until the provider settles. But there's a trick...
    
    // Actually for HODL invoices, we use the ASYNC router API:
    stream, err := fp.routerClient.SendPaymentV2(ctx, &routerrpc.SendPaymentRequest{
        PaymentRequest: paymentRequest,
        TimeoutSeconds: 120,
    })
    
    // This returns a STREAM of payment state updates:
    for {
        update, err := stream.Recv()
        if err != nil {
            return nil, err
        }
        
        switch update.Status {
        case lnrpc.Payment_IN_FLIGHT:
            // HTLC is being routed through the network
            log.Println("Payment in flight...")
            
        case lnrpc.Payment_SUCCEEDED:
            // Provider settled! We have the preimage!
            log.Printf("Payment settled! Preimage: %x", update.PaymentPreimage)
            return update.PaymentPreimage, nil
            
        case lnrpc.Payment_FAILED:
            return nil, fmt.Errorf("payment failed: %s", update.FailureReason)
        }
    }
}
```

**What's happening on the Lightning Network:**

```
Client LND                    Lightning Network               Provider LND
     │                              │                              │
     │── Create HTLC ─────────────►│                              │
     │   "I will pay 50 sat        │                              │
     │    to whoever reveals       │                              │
     │    preimage for hash        │                              │
     │    abc123..."               │                              │
     │                              │── Forward HTLC ────────────►│
     │                              │                              │
     │                              │   Provider LND sees:         │
     │                              │   "Someone wants to pay      │
     │                              │    50 sat for hash abc123"   │
     │                              │                              │
     │                              │   State: ACCEPTED            │
     │                              │   (funds are LOCKED but      │
     │                              │    not yet SETTLED)           │
     │                              │                              │
     │   At this point:                                            │
     │   - Client's 50 sats are LOCKED (can't spend elsewhere)    │
     │   - Provider hasn't received them yet                       │
     │   - Only the provider's Financial Pod knows the preimage    │
     │   - If nobody reveals preimage within timeout → REFUND      │
```

### Phase E: Provider Subscribes to Invoice State

While the client is paying, the provider FP is watching for the payment:

```go
func (fp *ProviderFinancialPod) watchForPayment(rhash []byte) {
    // Subscribe to state changes for this specific invoice
    stream, err := fp.invoicesClient.SubscribeSingleInvoice(ctx,
        &invoicesrpc.SubscribeSingleInvoiceRequest{
            RHash: rhash,
        },
    )
    
    for {
        invoice, err := stream.Recv()
        if err != nil {
            return
        }
        
        switch invoice.State {
        case lnrpc.Invoice_OPEN:
            // Invoice created, waiting for payment
            log.Println("Invoice OPEN, waiting...")
            
        case lnrpc.Invoice_ACCEPTED:
            // ★ THIS IS THE KEY STATE ★
            // Client has paid! HTLC is locked!
            // But funds are NOT settled yet — we control settlement.
            log.Println("HTLC ACCEPTED! Funds locked. Ready for compute.")
            
            // NOW it's safe to do the expensive compute
            // because even if compute fails, we can cancel
            // and the client gets their money back
            
        case lnrpc.Invoice_SETTLED:
            log.Println("Invoice SETTLED. Funds received.")
            
        case lnrpc.Invoice_CANCELLED:
            log.Println("Invoice CANCELLED. Funds returned to client.")
        }
    }
}
```

### Phase F: Compute → Settle or Cancel

```go
// After HTLC is ACCEPTED (funds locked)...

// 1. Dispatch compute to the Agent
result, computeErr := fp.agent.RunJob(jobSpec)

if computeErr != nil {
    // Compute FAILED → Cancel the invoice → Client gets refund
    _, err := fp.invoicesClient.CancelInvoice(ctx,
        &invoicesrpc.CancelInvoiceMsg{
            PaymentHash: rhash,
        },
    )
    // Client's LND automatically gets the HTLC refunded
    // No money was lost by anyone
    
} else {
    // Compute SUCCEEDED → Settle the invoice → Provider gets paid
    _, err := fp.invoicesClient.SettleInvoice(ctx,
        &invoicesrpc.SettleInvoiceMsg{
            Preimage: preimage,  // Reveal the secret!
        },
    )
    // LND verifies SHA256(preimage) == hash
    // If match: funds transfer from Client → Provider
    // The preimage propagates back through the Lightning Network
    // to the Client's LND node
}
```

**What happens when `SettleInvoice` is called:**

```
Provider FP                  Provider LND              Client LND
     │                            │                         │
     │── SettleInvoice ─────────►│                         │
     │   (reveals preimage)       │                         │
     │                            │                         │
     │   LND verifies:            │                         │
     │   SHA256(preimage)==hash?   │                         │
     │   YES ✓                    │                         │
     │                            │                         │
     │                            │── Reveal preimage ────►│
     │                            │   to upstream HTLC      │
     │                            │                         │
     │                            │   Client LND:           │
     │                            │   "Preimage revealed!   │
     │                            │    Payment complete."   │
     │                            │                         │
     │   Provider balance: +50    │   Client balance: -50   │
     │                            │                         │
```

### Phase G: Client Gets Result + Preimage

Back on the client side, the `SendPaymentV2` stream receives the `SUCCEEDED` status with the preimage:

```go
// Client FP now has the preimage from the payment response
preimage := paymentUpdate.PaymentPreimage

// Retry the original gRPC call with macaroon + preimage
ctx = metadata.AppendToOutgoingContext(ctx,
    "macaroon", macHex,
    "preimage", hex.EncodeToString(preimage),
)

// This time, the L402 interceptor on the Provider will:
// 1. Find the macaroon header ✓
// 2. Verify HMAC signature ✓
// 3. Check expiry caveat ✓
// 4. Find the preimage header ✓
// 5. Verify SHA256(preimage) == payment hash in macaroon ✓
// 6. Allow the call through to the actual handler ✓

result, err := providerClient.CallService(ctx, &pb.CallServiceRequest{
    JobSpec: jobSpec,
})
// result contains the compute output
```

---

## 4. Complete Timeline — Everything in Order

```
Time    Who              What                           LND API Call
─────   ──────────────   ────────────────────────────   ──────────────────────
T+0     Client Agent     "I need YOLOv9 inference"      (none — internal)
T+1     Client FP        Calls Provider FP              gRPC: CallService
T+2     Provider FP      No auth → generate preimage    (none — crypto/rand)
T+3     Provider FP      Hash the preimage              (none — SHA256)
T+4     Provider FP      Create HODL invoice             invoicesrpc.AddHoldInvoice
T+5     Provider FP      Bake macaroon                  (none — macaroon.New)
T+6     Provider FP      Store hold in SQLite            (none — SQL INSERT)
T+7     Provider FP      Return 402 to Client            gRPC status error
T+8     Client FP        Check budget                   (none — internal)
T+9     Client FP        Pay invoice                     routerrpc.SendPaymentV2
T+10    Lightning        HTLC routes through network     (automatic)
T+11    Provider LND     HTLC arrives, state=ACCEPTED    (automatic)
T+12    Provider FP      Sees ACCEPTED via stream        invoicesrpc.SubscribeSingleInvoice
T+13    Provider FP      Dispatches compute to Agent     (none — internal)
T+14    Provider Agent   Runs YOLOv9, returns result     (none — ML inference)
T+15    Provider FP      Settle HODL invoice             invoicesrpc.SettleInvoice
T+16    Lightning        Preimage propagates back        (automatic)
T+17    Client LND       Payment status → SUCCEEDED      (automatic)
T+18    Client FP        Gets preimage from payment      (from stream.Recv)
T+19    Client FP        Retries with macaroon+preimage  gRPC: CallService (retry)
T+20    Provider FP      L402 interceptor → PASS         (verify macaroon+preimage)
T+21    Provider FP      Returns compute result          gRPC response
T+22    Client FP        Forwards to Client Agent        (none — internal)
T+23    Client FP        Logs in ledger                  (none — SQL INSERT)
T+24    Provider FP      Logs in ledger                  (none — SQL INSERT)
T+25    Both             Done. Both ledgers agree.       ✓
```

---

## 5. What the Current Code Has vs What's Needed

```
                          CURRENT CODE              REAL IMPLEMENTATION
                          ════════════              ═══════════════════
TLS Connection            grpc.WithInsecure()       credentials.NewClientTLSFromCert()
Macaroon Auth             (missing)                 PerRPCCredentials with hex macaroon
HODL Invoice Create       lnrpc.AddInvoice          invoicesrpc.AddHoldInvoice
                          + fake IsHodl field        + real hash parameter
HODL Invoice Settle       (missing)                 invoicesrpc.SettleInvoice(preimage)
HODL Invoice Cancel       (missing)                 invoicesrpc.CancelInvoice(hash)
Invoice State Watch       (missing)                 invoicesrpc.SubscribeSingleInvoice
Payment Send              (missing)                 routerrpc.SendPaymentV2 (streaming)
Macaroon Verify           HMAC only                 HMAC + caveat predicates
Preimage ↔ Hash           demo_l402 has it          Same (SHA256 verify)
Ledger                    ✅ Working (SQLite)        Same (add missing columns)
Budget Manager            Has underflow bug          Fix int64 comparison
```

The gap is clear: **5 missing LND API calls** and **2 bug fixes** stand between the current code and a working system.
