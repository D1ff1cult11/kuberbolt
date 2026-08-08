# Lightning Node Test Environment (2-Node Setup)

This directory contains a complete local 2-node **Lightning Network (LND)** setup running on **Bitcoin Core Regtest** using **Docker Compose** and **Golang**.

## Structure

- `docker-compose.yml`: Provisions 3 containers:
  - `bitcoind`: Bitcoin Core node in regtest mode.
  - `lnd1`: Lightning Node for User 1 (Alice).
  - `lnd2`: Lightning Node for User 2 (Bob).
- `test-data.json`: Stores credentials, public keys, P2P connection strings, macaroon hex tokens, and channel parameter defaults.
- `main.go`: Go integration program that:
  - Connects to the Docker containers.
  - Mines regtest Bitcoin blocks.
  - Automatically fetches pubkeys and macaroon hex strings from `lnd1` and `lnd2`.
  - Updates `test-data.json`.
  - Funds User 1's wallet.
  - Connects `lnd1` to `lnd2` and opens a Lightning payment channel.
  - Mines block confirmations.

## How to Run

### Step 1: Start Docker Containers
```bash
docker compose up -d
```

### Step 2: Run the Go Integration Script
```bash
go run main.go
```

or via Go container / local Go installation:
```bash
docker run --rm -v $(pwd):/app -w /app golang:1.21 go run main.go
```

### Step 3: Inspect `test-data.json`
`test-data.json` will be populated with the live public keys, P2P addresses, and hex macaroons of User 1 and User 2:
```json
{
  "user1_node": {
    "alias": "User1_Alice",
    "pubkey": "<User 1 PubKey>",
    "p2p_address": "<User 1 PubKey>@kuberbolt-lnd1:9735",
    "grpc_endpoint": "localhost:10009",
    "rest_endpoint": "https://localhost:8080",
    "macaroon_hex": "<Macaroon Hex>",
    "tls_cert_path": "./lnd1_data/tls.cert"
  },
  "user2_node": {
    "alias": "User2_Bob",
    "pubkey": "<User 2 PubKey>",
    "p2p_address": "<User 2 PubKey>@kuberbolt-lnd2:9735",
    "grpc_endpoint": "localhost:10010",
    "rest_endpoint": "https://localhost:8081",
    "macaroon_hex": "<Macaroon Hex>",
    "tls_cert_path": "./lnd2_data/tls.cert"
  },
  "test_channel_params": {
    "funding_amount_sats": 100000,
    "push_satoshis": 1000,
    "target_conf": 1
  }
}
```

### Useful CLI Debug Commands
- Check User 1 info: `docker compose exec lnd1 lncli --network=regtest getinfo`
- Check User 2 info: `docker compose exec lnd2 lncli --network=regtest getinfo`
- List channels: `docker compose exec lnd1 lncli --network=regtest listchannels`
- Mine a block manually: `docker compose exec bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpassword generatetoaddress 1 $(docker compose exec lnd1 lncli --network=regtest newaddress p2wkh | jq -r .address)`
