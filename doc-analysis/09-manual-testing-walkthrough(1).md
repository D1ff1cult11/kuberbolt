# Manual Testing Walkthrough: L402 HODL Flow

This guide walks you through the steps to manually test the Financial Pod's L402 implementation against real Lightning Network Daemon (LND) nodes running locally.

## Prerequisite: Spin Up the LND Cluster

Before the Financial Pod can issue or pay invoices, you need a local Lightning Network (regtest).

1. Open a terminal in the `mock_work/lightning-infra/` directory.
2. Start the cluster:
   ```bash
   docker compose -f docker-compose.lnd.yml up -d
   ```
3. This spins up **Alice** (our Provider) and **Bob** (our Client) along with a local Bitcoin `btcd` backend.
4. **Fund & Open Channel**: Bob must have liquidity to pay Alice. You can either use a GUI tool like [Polar](https://lightningpolar.com/) to attach to these nodes and open a channel, or use `lncli` within the docker containers to generate blocks, fund Bob's wallet, and open a channel to Alice.

Once Alice and Bob have an active, funded channel, you can proceed.

---

## Option A: Automated E2E Test (Recommended)

The fastest way to witness the full L402 state machine in action is to run the integration test we built (`integration_test.go`). This test acts as a macro that drives both Alice's and Bob's LND nodes through the exact HODL flow the Financial Pod uses.

1. Open a terminal in the `mock_work/agent-payment-network/agent-pod/financial-pod` directory.
2. Export the connection details for your local Docker LND nodes:
   *(Adjust paths based on where Docker maps the LND volumes)*
   
   **Windows (PowerShell):**
   ```powershell
   $env:ALICE_HOST="127.0.0.1"
   $env:ALICE_GRPC_PORT="10001"
   $env:ALICE_TLS_CERT="C:\path\to\alice\tls.cert"
   $env:ALICE_MACAROON="C:\path\to\alice\data\chain\bitcoin\regtest\admin.macaroon"
   
   $env:BOB_HOST="127.0.0.1"
   $env:BOB_GRPC_PORT="10002"
   $env:BOB_TLS_CERT="C:\path\to\bob\tls.cert"
   $env:BOB_MACAROON="C:\path\to\bob\data\chain\bitcoin\regtest\admin.macaroon"
   ```
3. Run the integration test:
   ```bash
   go test ./internal/gateway/ -v -run TestL402Integration
   ```

### What You Will See in the Output
You will see the complete L402 state machine log out step-by-step:
1. **Phase 1:** Alice generates a 32-byte secret preimage, hashes it (SHA256), and creates a HODL invoice using just the hash.
2. **Phase 2:** Alice subscribes to the invoice state stream on her LND node.
3. **Phase 3:** Bob calls `SendPayment` to pay the invoice. His LND locks the funds into an HTLC.
4. **Phase 4:** Alice sees the invoice state transition to `ACCEPTED`. (The funds are now locked and guaranteed).
5. **Phase 5:** Alice executes her simulated "compute task", then calls `SettleInvoice` by revealing the secret preimage.
6. **Phase 6 & 7:** Bob's `SendPayment` call completes successfully and returns the preimage. The test verifies `SHA256(preimage) == hash`.

---

## Option B: Full Manual Server Execution

If you want to run the actual Financial Pod binaries and interact with them via gRPC, follow these steps:

### 1. Initialize the Financial Pods
Create configurations for both Alice (Provider) and Bob (Client).

```bash
cd mock_work/agent-payment-network/agent-pod/financial-pod

# Initialize Alice
go run ./cmd/financialpod -init -name Alice

# Initialize Bob
go run ./cmd/financialpod -init -name Bob
```
This generates config files at `~/.kuberbolt/Alice/config.yaml` and `~/.kuberbolt/Bob/config.yaml`.

### 2. Edit Configurations
Open the generated `config.yaml` files.
- **For Alice**: Update the `lightning` section to point to her Docker `tls.cert` and `admin.macaroon`. Ensure her `grpc_port` is set to `6001`.
- **For Bob**: Update his `lightning` section to point to his Docker credentials. Change his `grpc_port` to `6002` to avoid port collisions.

### 3. Start Alice (Provider)
In terminal 1:
```bash
go run ./cmd/financialpod -name Alice
```
*You will see Alice connect to LND, open her SQLite ledger, and begin listening on `0.0.0.0:6001`.*

### 4. Start Bob (Client) & Trigger the Flow
Currently, the Financial Pod doesn't have an external REST API (that comes in Phase 3 with the Python SDK). To trigger Bob to pay Alice manually, you can use a gRPC client like [grpcurl](https://github.com/fullstorydev/grpcurl) or [Postman](https://www.postman.com/) (with gRPC support).

1. Import `agent_service.proto` into Postman.
2. Create a gRPC request to `127.0.0.1:6001` (Alice).
3. Call the `CallService` method with an empty payload.
4. **What you will see**: Alice will immediately reject the request with a gRPC Error containing the `402 Payment Required` challenge (the HODL Invoice + baked Macaroon).

To simulate Bob paying it:
1. Make a gRPC call to `127.0.0.1:6002` (Bob) using the internal `PayHoldInvoice` method, passing Alice's invoice string.
2. Bob's pod will pay the invoice, locking the HTLC.
3. If you check Alice's logs, you will see her detect the `ACCEPTED` state, execute the compute, and settle the invoice.
4. Bob's gRPC call will return the secret `preimage`.
5. You can then make a final call to Alice's `CallService`, but this time include the `macaroon` and `preimage` as headers. Alice will verify the cryptographic proof and return the compute result!
