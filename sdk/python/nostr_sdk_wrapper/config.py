"""
Agent configuration: loads $KUBERBOLT_HOME/<agent>/config.yaml.

The schema is shared with the Go financial pod (internal/config) and is
documented in kuberbolt-config/agent.example.yaml. There are deliberately no
defaults for relays, hosts, ports or timeouts: a missing value raises
ConfigError naming the field.

Environment overrides:
  KUBERBOLT_HOME    base directory (falls back to ~/.kuberbolt, same as the Go pod)
  KUBERBOLT_AGENT   agent name, when not passed explicitly
  KUBERBOLT_RELAYS  comma-separated relay URLs, replaces network.nostr_relays
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROLES = ("client", "merchant")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ServiceConfig:
    name: str
    category: str
    description: str
    price_msat: int
    price_unit: str
    timeout_sec: int

    @property
    def price_sats(self) -> int:
        return self.price_msat // 1000


@dataclass(frozen=True)
class KuberboltConfig:
    agent_dir: Path
    name: str
    role: str
    identity_path: Path
    ledger_path: Path
    display_name: str
    about: str | None
    picture_url: str | None
    lightning_address: str | None
    services: list[ServiceConfig]
    relays: list[str]
    relay_connect_wait_sec: float
    handshake_timeout_sec: int
    discovery_timeout_sec: int
    endpoint_poll_sec: int | None
    grpc_port: int
    public_host: str | None
    pod_addr: str | None
    brain: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def require(self, value: Any, path: str) -> Any:
        """Return `value`, or raise ConfigError if it is empty. For
        role-specific fields (e.g. public_host for merchants) that callers
        need to check at the point of use."""
        if value in (None, "", 0, []):
            raise ConfigError(f"{self.agent_dir / 'config.yaml'}: {path} is required")
        return value


def kuberbolt_home() -> Path:
    env = os.getenv("KUBERBOLT_HOME")
    return Path(env).expanduser() if env else Path.home() / ".kuberbolt"


def agent_dir(agent_name: str | None = None, home: str | Path | None = None) -> Path:
    name = agent_name or os.getenv("KUBERBOLT_AGENT")
    if not name:
        raise ConfigError("agent name required: pass --name or set KUBERBOLT_AGENT")
    base = Path(home).expanduser() if home else kuberbolt_home()
    return base / name


def _get(data: dict, path: str, src: Path, required: bool = True) -> Any:
    cur: Any = data
    for part in path.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    if required and cur in (None, "", 0, []):
        raise ConfigError(f"{src}: {path} is required")
    return cur or None


def _resolve(base: Path, value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else base / p


def load_config(agent_name: str | None = None, home: str | Path | None = None) -> KuberboltConfig:
    directory = agent_dir(agent_name, home)
    src = directory / "config.yaml"
    if not src.exists():
        raise ConfigError(f"{src} not found: run `kuberbolt init --name {directory.name}`")
    data = yaml.safe_load(src.read_text()) or {}

    role = _get(data, "agent.role", src)
    if role not in ROLES:
        raise ConfigError(f"{src}: agent.role must be one of {ROLES}, got {role!r}")

    relays_env = os.getenv("KUBERBOLT_RELAYS")
    relays = ([r.strip() for r in relays_env.split(",") if r.strip()] if relays_env
              else _get(data, "network.nostr_relays", src))
    if not relays:
        raise ConfigError(f"{src}: network.nostr_relays is required")

    services = []
    for i, s in enumerate(data.get("services") or []):
        services.append(ServiceConfig(
            name=_get(s, "name", src),
            category=_get(s, "category", src),
            description=_get(s, "description", src),
            price_msat=int(_get(s, "price_msat", src)),
            price_unit=_get(s, "price_unit", src),
            timeout_sec=int(_get(s, "timeout_sec", src)),
        ))
    if role == "merchant" and not services:
        raise ConfigError(f"{src}: merchants need at least one entry in services")

    return KuberboltConfig(
        agent_dir=directory,
        name=_get(data, "agent.name", src),
        role=role,
        identity_path=_resolve(directory, _get(data, "agent.identity_file", src)),
        ledger_path=_resolve(directory, _get(data, "agent.ledger_path", src)),
        display_name=_get(data, "agent.display_name", src),
        about=_get(data, "agent.about", src, required=False),
        picture_url=_get(data, "agent.picture_url", src, required=False),
        lightning_address=_get(data, "agent.lightning_address", src, required=False),
        services=services,
        relays=list(relays),
        relay_connect_wait_sec=float(_get(data, "network.relay_connect_wait_sec", src)),
        handshake_timeout_sec=int(_get(data, "network.handshake_timeout_sec", src)),
        discovery_timeout_sec=int(_get(data, "network.discovery_timeout_sec", src)),
        endpoint_poll_sec=_get(data, "network.endpoint_poll_sec", src, required=False),
        grpc_port=int(_get(data, "network.grpc_port", src)),
        public_host=_get(data, "network.public_host", src, required=False),
        pod_addr=_get(data, "network.pod_addr", src, required=False),
        brain=data.get("brain") or {},
        raw=data,
    )
