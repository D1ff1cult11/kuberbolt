"""`kuberbolt` command line: set up and run one agent from its local
$KUBERBOLT_HOME/<agent>/ directory, talking directly to Nostr relays."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import identity
from .agent import KuberboltAgent
from .config import ROLES, ConfigError, agent_dir, load_config


def _init(args) -> None:
    directory = identity.init_agent(args.name, args.role, home=args.home, nsec=args.nsec)
    keys = identity.load_identity(directory / "identity.json")
    print(f"agent dir: {directory}")
    print(f"npub:      {keys.public_key().to_bech32()}")
    print(f"next: fill in {directory / 'config.yaml'}")


def _whoami(args) -> None:
    path = agent_dir(args.name, args.home) / "identity.json"
    if not path.exists():
        raise ConfigError(f"{path} not found: run `kuberbolt init --name {path.parent.name}`")
    keys = identity.load_identity(path)
    print(f"npub: {keys.public_key().to_bech32()}")
    print(f"hex:  {keys.public_key().to_hex()}")
    if args.show_secret:
        print(f"nsec: {keys.secret_key().to_bech32()}")


async def _with_agent(args, fn):
    agent = await KuberboltAgent.from_config(load_config(args.name, args.home))
    try:
        return await fn(agent)
    finally:
        await agent.disconnect()


def _register(args) -> None:
    result = asyncio.run(_with_agent(args, lambda a: a.register_from_config()))
    print(json.dumps(result, indent=2))


def _discover(args) -> None:
    providers = asyncio.run(_with_agent(args, lambda a: a.discover(args.category, price_max=args.price_max)))
    if args.json:
        print(json.dumps(providers, indent=2))
        return
    for p in providers:
        print(f"{p['nostr_pubkey']}  {p['price_sats']} sats {p['price_unit']}  {p['name']}: {p['service_name']}")


def _resolve(args) -> None:
    reply = asyncio.run(_with_agent(args, lambda a: a.request_endpoint(args.provider_pubkey, job_id=args.job_id)))
    if reply is None:
        sys.exit("kuberbolt: no reply from provider before handshake_timeout_sec")
    print(json.dumps(reply))


def _serve_endpoint(args) -> None:
    cfg = load_config(args.name, args.home)
    host = cfg.require(cfg.public_host, "network.public_host")
    port = cfg.require(cfg.grpc_port, "network.grpc_port")

    async def serve(agent):
        await agent.serve_endpoint_requests(host, port, poll_interval=int(cfg.require(cfg.endpoint_poll_sec, "network.endpoint_poll_sec")), db_path=cfg.ledger_path)

    asyncio.run(_with_agent(args, serve))


def main(argv: list[str] | None = None) -> None:
    # --name/--home are accepted before or after the subcommand.
    name_help, home_help = "agent name (else KUBERBOLT_AGENT)", "base dir (else KUBERBOLT_HOME or ~/.kuberbolt)"
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--name", default=argparse.SUPPRESS, help=name_help)
    common.add_argument("--home", default=argparse.SUPPRESS, help=home_help)
    parser = argparse.ArgumentParser(prog="kuberbolt")
    parser.add_argument("--name", help=name_help)
    parser.add_argument("--home", help=home_help)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", parents=[common], help="create the agent dir, identity and config skeleton")
    p.add_argument("--role", required=True, choices=ROLES)
    p.add_argument("--nsec", help="import this key instead of generating one")
    p.set_defaults(fn=_init)

    p = sub.add_parser("whoami", parents=[common], help="print this agent's public key")
    p.add_argument("--show-secret", action="store_true", help="also print the nsec")
    p.set_defaults(fn=_whoami)

    p = sub.add_parser("register", parents=[common], help="publish profile (and listing) from config")
    p.set_defaults(fn=_register)

    p = sub.add_parser("discover", parents=[common], help="find service listings by category")
    p.add_argument("--category", required=True)
    p.add_argument("--price-max", type=int)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_discover)

    p = sub.add_parser("resolve", parents=[common], help="ask a provider for its endpoint")
    p.add_argument("provider_pubkey")
    p.add_argument("--job-id")
    p.set_defaults(fn=_resolve)

    p = sub.add_parser("serve-endpoint", parents=[common], help="merchant: answer endpoint requests")
    p.set_defaults(fn=_serve_endpoint)

    args = parser.parse_args(argv)
    try:
        args.fn(args)
    except ConfigError as e:
        sys.exit(f"kuberbolt: {e}")
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
