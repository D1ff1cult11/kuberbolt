"""Shared fixtures for SDK tests. Nothing here touches a real relay."""

from __future__ import annotations

import pytest
import yaml


def _write_config(directory, **overrides):
    """Write a complete, valid merchant config.yaml into `directory`."""
    data = {
        "agent": {
            "name": directory.name,
            "role": "merchant",
            "identity_file": "identity.json",
            "ledger_path": "ledger.db",
            "display_name": "Test Seller",
        },
        "services": [{
            "name": "text-summarization",
            "category": "ai-text",
            "description": "Summarizes text",
            "price_msat": 50_000,
            "price_unit": "per_request",
            "timeout_sec": 30,
        }],
        "network": {
            "grpc_port": 6001,
            "public_host": "10.0.0.5",
            "nostr_relays": ["wss://relay.test"],
            "relay_connect_wait_sec": 0.01,
            "handshake_timeout_sec": 2,
            "discovery_timeout_sec": 2,
        },
    }
    for dotted, value in overrides.items():
        *parents, leaf = dotted.split("__")
        node = data
        for part in parents:
            node = node[part]
        node[leaf] = value
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "config.yaml").write_text(yaml.safe_dump(data))
    return directory


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.delenv("KUBERBOLT_AGENT", raising=False)
    monkeypatch.delenv("KUBERBOLT_RELAYS", raising=False)
    monkeypatch.setenv("KUBERBOLT_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def write_config():
    return _write_config
