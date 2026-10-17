# Kuberbolt Python SDK

A local library and CLI for one Kuberbolt agent. It creates the agent's Nostr identity on the agent's own machine, publishes its profile and service listing, discovers other agents, runs the NIP-44 endpoint handshake and publishes feedback. It talks directly to Nostr relays; no server is involved.

## Install

```bash
pip install -e sdk/python            # add [dev] for pytest
```

## Agent directory

Everything for one agent lives in `$KUBERBOLT_HOME/<agent>/`. `KUBERBOLT_HOME` defaults to `~/.kuberbolt`.

| File | What |
|------|------|
| `config.yaml` | The only source of settings. The schema is `kuberbolt-config/agent.example.yaml`, and the Go financial pod reads the same file. |
| `identity.json` | The Nostr keypair, mode 0600. Only `kuberbolt init` creates it. |
| `ledger.db` | Local state, such as handshake requests already answered. |

There are no built-in defaults for relays, hosts, ports or timeouts. A missing value raises `ConfigError` naming the setting. Env overrides: `KUBERBOLT_AGENT` (agent name), `KUBERBOLT_HOME`, and `KUBERBOLT_RELAYS` (comma-separated relays).

## CLI

```bash
kuberbolt init --name <agent> --role client|merchant [--nsec nsec1...]  # create dir, key, config skeleton (never overwrites a key)
kuberbolt whoami [--show-secret]                 # print npub/hex (nsec only with --show-secret)
kuberbolt register                               # publish kind 0 profile, plus the kind 31990 listing (merchants: exactly one service)
kuberbolt discover --category <c> [--price-max N] [--json]
kuberbolt resolve <provider_pubkey> [--job-id ID]   # ask a provider for its endpoint over NIP-44
kuberbolt serve-endpoint                         # merchant: answer resolve requests with network.public_host:grpc_port
```
`--name` and `--home` can go before or after the subcommand. Without `--name`, the CLI uses `KUBERBOLT_AGENT`.

## Library

```python
from nostr_sdk_wrapper.agent import KuberboltAgent
from nostr_sdk_wrapper.config import load_config

agent = await KuberboltAgent.from_config(load_config("buyer"))
try:
    providers = await agent.discover("summarization")
    endpoint = await agent.request_endpoint(providers[0]["nostr_pubkey"])  # {"job_id", "host", "port"} or None
finally:
    await agent.disconnect()
```

The event kinds are listed in `shared/nostr-kinds.md`.
