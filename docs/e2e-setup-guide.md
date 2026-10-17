# Kuberbolt End-to-End Setup Guide (2 machines, no server)

Two peers. Neither one is a server for the other.

| Machine | Role | Runs |
|---------|------|------|
| **A** | Buyer (`client`) | LND (Alice) + Go financial pod + buyer brain (`agent-pod/brain/app/buyer_agent.py`) |
| **B** | Seller (`merchant`) | LND (Bob) + Go financial pod + seller brain (`agent-pod/brain/app/seller_agent.py`) |

Each machine has its own `~/.kuberbolt/<agent>/` directory (`config.yaml`, `identity.json`, `ledger.db`). Each agent creates its own Nostr key locally with `kuberbolt init`, and the key never leaves the machine. The agents find each other through public Nostr relays. The buyer's pod pays the seller's pod directly over Lightning.

```
                 Nostr relays (kind 0, 31990, 21000 NIP-44, 7000)
                  ▲                                         ▲
   Machine A      │                                         │      Machine B
   buyer brain ── KuberboltAgent (local SDK)    KuberboltAgent (local SDK) ── seller brain
        │ grpcurl                                                               ▲ HTTP /compute
        ▼                                                                       │
   financial pod ──────────── gRPC CallService + L402 ──────────────▶ financial pod
        │                                                                       │
   LND Alice ════════════════ Lightning channel (HODL invoice) ═══════════ LND Bob
```

Regtest needs one `bitcoind`, and this guide runs it on Machine B. That `bitcoind` is just the test blockchain, not a Kuberbolt service. On testnet or mainnet, each LND uses the public chain instead.

---

## 0. Prerequisites (both machines)

- Python 3.12+, Go 1.21+, Docker, Git. Both machines must be on the same LAN.
- Machine A: [`grpcurl`](https://github.com/fullstorydev/grpcurl) on `PATH`. The buyer brain uses it to call its own pod.
- Both machines need a `GOOGLE_API_KEY` for Gemini. Both brains use an LLM.
- Note each machine's LAN IP: `ipconfig getifaddr en0` (macOS), `hostname -I` (Linux), `(Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias Wi-Fi).IPAddress` (Windows). Below, these are `<A_IP>` and `<B_IP>`.

```bash
git clone https://github.com/devlup-labs/kuberbolt.git && cd kuberbolt
python3 -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e sdk/python -r agent-pod/brain/requirements.txt
cp .env.example .env                                  # fill in KUBERBOLT_AGENT and GOOGLE_API_KEY
```

The bash scripts in `scripts/` need a POSIX shell. On Windows, use WSL or Git Bash, or run the commands the scripts run by hand. `scripts/start_financial_pod.ps1` is the PowerShell version of the pod script.

---

## 1. Lightning (regtest)

**Machine B:** start `bitcoind` and Bob from the repo's compose file. Bob's gRPC port is published on host port `10002`, and his p2p port on `9736`.
```bash
docker compose -f lightning-infra/docker-compose.lnd.yml up -d bitcoind bob
docker exec bob lncli --network=regtest getinfo        # note identity_pubkey = <BOB_PUBKEY>
```

**Machine A:** start Alice, pointed at Machine B's `bitcoind`.
```bash
docker run -d --name alice -p 10009:10009 -p 9735:9735 -v "$PWD/alice-data:/root/.lnd" \
  lightninglabs/lnd:v0.17.4-beta --noseedbackup --trickledelay=5000 --alias=alice \
  --bitcoin.active --bitcoin.regtest --bitcoin.node=bitcoind \
  --bitcoind.rpchost=<B_IP>:18443 --bitcoind.rpcuser=devuser --bitcoind.rpcpass=devpass \
  --bitcoind.zmqpubrawblock=tcp://<B_IP>:28332 --bitcoind.zmqpubrawtx=tcp://<B_IP>:28333 \
  --rpclisten=0.0.0.0:10009 --listen=0.0.0.0:9735 --tlsextradomain=localhost
docker exec alice lncli --network=regtest newaddress p2wkh    # note <ALICE_ADDR>
```

**Machine B:** mine 101 blocks to Alice so she has coins to spend.
```bash
docker exec bitcoind bitcoin-cli -regtest -rpcuser=devuser -rpcpassword=devpass generatetoaddress 101 <ALICE_ADDR>
```

**Machine A:** open a channel to Bob.
```bash
docker exec alice lncli --network=regtest walletbalance        # non-zero confirmed_balance
docker exec alice lncli --network=regtest connect <BOB_PUBKEY>@<B_IP>:9736
docker exec alice lncli --network=regtest openchannel --node_key=<BOB_PUBKEY> --local_amt=500000
```

**Machine B:** mine 6 blocks to confirm the channel. Then, on Machine A, run `listchannels` and check that it shows `"active": true`.
```bash
docker exec bitcoind bitcoin-cli -regtest -rpcuser=devuser -rpcpassword=devpass generatetoaddress 6 <ALICE_ADDR>
```

The LND credentials are in the Docker data directories. The financial pod reads them from the paths you set in `config.yaml`:
- Machine A: `<repo>/alice-data/tls.cert` and `<repo>/alice-data/data/chain/bitcoin/regtest/admin.macaroon`
- Machine B: `<repo>/lightning-infra/bob-data/tls.cert` and `<repo>/lightning-infra/bob-data/data/chain/bitcoin/regtest/admin.macaroon`

---

## 2. Create each agent's identity and config

Every value in `config.yaml` is required unless the template marks it optional. Nothing falls back to a default: a missing value stops the process with an error that names it. The schema is `kuberbolt-config/agent.example.yaml`.

**Machine B (seller):**
```bash
kuberbolt init --name seller --role merchant     # prints the npub; writes ~/.kuberbolt/seller/
```
Then edit `~/.kuberbolt/seller/config.yaml`. These values are examples; use your own:
```yaml
agent:
  name: seller
  role: merchant
  identity_file: identity.json
  ledger_path: ledger.db
  display_name: "Summarizer B"
services:
  - name: text-summarization        # passed to the brain as service_kind
    category: summarization         # buyers discover by this
    description: "Summarizes text with Gemini"
    price_msat: 10000
    price_unit: per_request
    timeout_sec: 60
    kind: 0
network:
  grpc_port: 6001
  public_host: "<B_IP>"             # what buyers dial
  nostr_relays: ["wss://nos.lol", "wss://relay.primal.net"]   # must accept and keep kind 21000 events
  relay_connect_wait_sec: 2
  handshake_timeout_sec: 30
  discovery_timeout_sec: 10
  endpoint_poll_sec: 5
brain:
  url: "http://127.0.0.1:8001"      # where the pod calls the brain
  listen_host: 127.0.0.1
  listen_port: 8001
  llm_model: gemini-2.0-flash
lightning:
  network: regtest
  lnd_host: 127.0.0.1
  lnd_grpc_port: 10002
  tls_cert_path: /abs/path/to/lightning-infra/bob-data/tls.cert
  macaroon_path: /abs/path/to/lightning-infra/bob-data/data/chain/bitcoin/regtest/admin.macaroon
budget:
  daily_limit_msat: 0               # merchants don't spend; only clients need limits
  monthly_limit_msat: 0
logging:
  level: info
  format: console
```

**Machine A (buyer):**
```bash
kuberbolt init --name buyer --role client
```
Edit `~/.kuberbolt/buyer/config.yaml` the same way, with these differences:
- `services: []`.
- `network.pod_addr: "127.0.0.1:6001"`: where the buyer brain reaches its own pod. It must match `network.grpc_port`.
- `public_host`, `endpoint_poll_sec` and the `brain` keys other than `llm_model` can stay empty.
- `lightning` points at Alice: `lnd_grpc_port: 10009` and the `alice-data` paths.
- Set a real budget, for example `daily_limit_msat: 1000000` and `monthly_limit_msat: 10000000`.

On both machines, set `KUBERBOLT_AGENT` (`seller` or `buyer`) and `GOOGLE_API_KEY` in `.env`. Check the identity with `kuberbolt whoami`.

---

## 3. Start the seller (Machine B, 2 terminals)

```bash
scripts/start_financial_pod.sh     # terminal 1: pod on network.grpc_port
scripts/start_seller.sh            # terminal 2: publishes profile + listing, serves /compute, answers handshakes
```
The seller registers itself on startup; it doesn't need a separate `kuberbolt register`. Port `grpc_port` must be reachable from Machine A, so allow it through the firewall.

## 4. Check the buyer can see the seller (Machine A)

```bash
kuberbolt discover --category summarization     # should list the seller's pubkey and price
kuberbolt resolve <SELLER_PUBKEY_HEX>           # should print {"job_id": ..., "host": "<B_IP>", "port": 6001}
```

## 5. Run the buyer (Machine A, 2 terminals)

```bash
scripts/start_financial_pod.sh                                   # terminal 1
scripts/start_buyer.sh "Find a summarization agent and summarize: <some text>"   # terminal 2
```
The buyer brain then: discovers providers → resolves the endpoint over NIP-44 → calls its local pod. The pod handles the 402 challenge, pays the HODL invoice, retries with the macaroon, and the seller's pod settles once compute succeeds. Finally the buyer publishes kind 7000 feedback.

---

## 6. Verify

- [ ] Buyer output contains the summary.
- [ ] Seller terminals show: handshake answered → challenge issued → HTLC accepted → `/compute` called → invoice settled.
- [ ] `docker exec alice lncli --network=regtest listpayments` shows a succeeded payment. `docker exec bob lncli --network=regtest listinvoices` shows it settled.
- [ ] Neither machine ran an API server, and only `~/.kuberbolt/<agent>/` holds the agent's key.

## Troubleshooting

- **`... is required` / `ConfigError`**: the error names the missing setting. Fill it in `config.yaml`.
- **`kuberbolt discover` returns nothing**: both agents must share at least one relay in `network.nostr_relays` (or `KUBERBOLT_RELAYS`), and the categories must match. Restart the seller to republish.
- **Relay requirements**: the handshake uses kind 21000. Nostr treats that kind as ephemeral, but the SDK polls for it, so the relay must keep it for a while. On 2026-10-17, `nos.lol` and `relay.primal.net` kept it for at least 20 s. `relay.damus.io` rejected publishes ("internal error"), and `relay.nostr.band` timed out.
- **`resolve` times out**: the seller brain isn't running, or it can't reach the relays. Raise `handshake_timeout_sec` if the relays are slow.
- **`Failed to call service`**: check that `grpcurl` is installed, that the buyer pod is up at `network.pod_addr`, and that `<B_IP>:<grpc_port>` is reachable from A.
- **LND connection failed**: check `lnd_host`/`lnd_grpc_port` and the absolute cert and macaroon paths. LND must be synced (`getinfo`).
- **Insufficient balance / no route**: the channel isn't active yet. Mine 6 more blocks on B.
- **Compute failed**: check `GOOGLE_API_KEY` and `brain.llm_model`. On a compute failure the seller's pod cancels the invoice, so the buyer isn't charged.
