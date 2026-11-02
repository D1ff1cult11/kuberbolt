# Two-machine run: commands in order

For the setup that is already in place:
- **Seller:** Tanay's Mac. Agent `seller`, LND Bob, `bitcoind` here, IP `192.168.1.7`.
- **Buyer:** the other Mac. Agent `buyer`, LND Alice.
- The Alice ⇄ Bob channel already exists. The agent keys and `config.yaml` files are already made.

First-time setup is in [e2e-setup-guide.md](e2e-setup-guide.md).

Run every command from the repo folder. Keep each long-running process in its own terminal.

---

## 0. Pre-flight: is Gemini answering? (both machines)

The agents can't work while Gemini is down, so check this first.

```bash
set -a; source .env; set +a
MODEL=$(grep llm_model ~/.kuberbolt/$KUBERBOLT_AGENT/config.yaml | awk '{print $2}')
curl -sS -m 60 -w '\nHTTP %{http_code} in %{time_total}s\n' -H "x-goog-api-key: $GOOGLE_API_KEY" \
  -H 'Content-Type: application/json' \
  "https://generativelanguage.googleapis.com/v1beta/models/$MODEL:generateContent" \
  -d '{"contents":[{"parts":[{"text":"Reply with exactly: ok"}]}]}' | grep -E '"text"|HTTP'
```
- **Need:** `"text": "ok"` and `HTTP 200` in a few seconds.
- **404 with no body, or slower than about 20 s:** don't start yet. Try another model from the list below, then set it as `brain.llm_model` in `~/.kuberbolt/<agent>/config.yaml`.
  ```bash
  curl -s -H "x-goog-api-key: $GOOGLE_API_KEY" "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200" | grep -o '"models/gemini[^"]*flash[^"]*"'
  ```

---

## 1. Seller Mac

**Terminal 0: blockchain and LND.** Open Docker Desktop first.
```bash
docker compose -f lightning-infra/docker-compose.lnd.yml up -d bitcoind bob
ipconfig getifaddr en0                       # must still be 192.168.1.7, otherwise see "IP changed" below
docker exec bitcoind bitcoin-cli -regtest -rpcuser=devuser -rpcpassword=devpass \
  generatetoaddress 1 $(docker exec bob lncli --network=regtest newaddress p2wkh | grep -o 'bcrt1[a-z0-9]*')
docker exec bob lncli --network=regtest getinfo | grep -E '"synced_to_chain"'   # true
```
Mining one block wakes up the chain tip, so both LNDs report "synced".

**Terminal 1: seller pod.**
```bash
source .venv/bin/activate
scripts/start_financial_pod.sh
```
Wait for `connected to LND {"alias": "bob" ...}` and `gRPC server listening {"addr": "0.0.0.0:6001"}`.

**Terminal 2: seller brain.**
```bash
source .venv/bin/activate
scripts/start_seller.sh
```
Wait for `Listing event: ...`, `Advertised Financial Pod: 192.168.1.7:6001` and `Uvicorn running on http://127.0.0.1:8001`.

---

## 2. Buyer Mac

**Terminal 0: update and start LND.** Open Docker Desktop first.
```bash
git pull                                      # latest fixes on the decentralize branch
source .venv/bin/activate
pip install -e sdk/python -r agent-pod/brain/requirements.txt    # only needed if requirements changed
docker start alice
sleep 15
docker exec alice lncli --network=regtest getinfo | grep -E '"synced_to_chain"|"num_active_channels"'   # true / 1
nc -vz -G 5 192.168.1.7 6001                  # must say "succeeded"
```

**Check the seller is visible** (same terminal):
```bash
export KUBERBOLT_AGENT=buyer
kuberbolt discover --category summarization
kuberbolt resolve e59b246858e83f9a7df265ab520e1c8d5ba7f69bab8e86619fe130abea901c1f
```
- `discover` should list `Summarizer B: text-summarization` at 10 sats.
- `resolve` should print `{"job_id": "...", "host": "192.168.1.7", "port": 6001}`.

**Terminal 1: buyer pod.**
```bash
source .venv/bin/activate
export KUBERBOLT_AGENT=buyer
scripts/start_financial_pod.sh
```
Wait for `connected to LND {"alias": "alice" ...}` and `gRPC server listening`.

**Terminal 2: buyer agent.**
```bash
source .venv/bin/activate
export KUBERBOLT_AGENT=buyer
scripts/start_buyer.sh "Find a summarization agent and summarize: Lightning lets two parties pay each other instantly by locking funds in a channel and updating balances off-chain."
```
The agent prints each step: `discover_providers`, `request_endpoint`, `call_service` (this pays), `publish_feedback`, then the summary.

---

## 3. Verify

On the **buyer**:
```bash
docker exec alice lncli --network=regtest listpayments | grep -E '"status"|"value_sat"' | tail -2   # SUCCEEDED, 10
```
On the **seller**:
```bash
docker exec bob lncli --network=regtest listinvoices | grep -E '"state"|"value"' | tail -2       # SETTLED, 10
```
The seller's pod log should show this sequence: `L402 CHALLENGE` → `HTLC LOCKED` → `PAYMENT SETTLED`.

## Payment-only test (no LLM on the buyer side)

To check that money moves even when the buyer's agent can't run, call the buyer's pod directly, with terminal 1 running:
```bash
grpcurl -plaintext -d "{\"provider_endpoint\":\"192.168.1.7:6001\",\"service_kind\":\"text-summarization\",\"job_spec\":\"$(printf '{"text":"hello"}' | base64)\"}" \
  127.0.0.1:6001 kuberbolt.v1.FinancialPodService/CallService
```
The seller's brain still uses Gemini to do the work. If Gemini is down, expect `compute failed, invoice cancelled`. That still proves the HODL lock and refund path, and no money moves.

## Shut down

- **Both:** press `Ctrl+C` in terminals 1 and 2.
- **Seller:** `docker compose -f lightning-infra/docker-compose.lnd.yml stop`
- **Buyer:** `docker stop alice`
- The channel, wallets and keys persist in `lightning-infra/bob-data`, `alice-data` and `~/.kuberbolt/<agent>/`.

## If something is off

| Symptom | Fix |
|---|---|
| **IP changed** (seller is no longer `192.168.1.7`) | **Seller:** set `network.public_host` in `~/.kuberbolt/seller/config.yaml` to the new IP and restart terminal 2. **Buyer:** Alice has the old IP built into her container, so recreate her: run `docker rm alice`, then rerun the `docker run -d --name alice ...` command from the setup guide with the new IP. Her data in `alice-data` is kept. Use the new IP everywhere `192.168.1.7` appears above. |
| Pod: `connection refused` to `127.0.0.1:10009` or `10002` | LND isn't running: `docker start alice`, or the compose `up` on the seller. |
| Pod: `x509: certificate signed by unknown authority` | `tls_cert_path` points to an old cert: `docker exec alice cat /root/.lnd/tls.cert > alice-data/tls.cert`. |
| `nc ... 6001` times out | Both Macs must be on the same Wi-Fi. If `nc` to `9736` and `18443` succeeds but `6001` doesn't, something on the seller Mac is blocking non-Docker processes. |
| `kuberbolt: agent name required` | `export KUBERBOLT_AGENT=buyer` (or `seller`). The CLI doesn't read `.env`. |
| `synced_to_chain: false` | Mine a block on the seller (terminal 0, the `generatetoaddress 1` line). |
| `channel not active` / `no route` | `docker exec alice lncli --network=regtest connect 028e27da6f12f750b9d769fc79b618de936605748aff6d0e70e568e98b1975368f@192.168.1.7:9736`, then mine a block. |
| Gemini 404 / no answer | Go back to the pre-flight check. Nothing else will work until it passes. |
