from pathlib import Path

import pytest

from nostr_sdk_wrapper.config import ConfigError, load_config


def test_load_full_config(home, write_config):
    write_config(home / "seller")
    cfg = load_config("seller")
    assert cfg.role == "merchant"
    assert cfg.identity_path == home / "seller" / "identity.json"
    assert cfg.relays == ["wss://relay.test"]
    assert cfg.services[0].price_sats == 50


def test_missing_config_file(home, write_config):
    with pytest.raises(ConfigError, match="kuberbolt init --name nobody"):
        load_config("nobody")


def test_agent_name_required(home, write_config):
    with pytest.raises(ConfigError, match="KUBERBOLT_AGENT"):
        load_config()


@pytest.mark.parametrize("field", ["network__nostr_relays", "network__handshake_timeout_sec", "agent__display_name"])
def test_required_field_missing(home, write_config, field):
    write_config(home / "seller", **{field: None})
    with pytest.raises(ConfigError, match=field.replace("__", ".")):
        load_config("seller")


def test_merchant_needs_service(home, write_config):
    write_config(home / "seller", services=[])
    with pytest.raises(ConfigError, match="services"):
        load_config("seller")


def test_relays_env_override(home, write_config, monkeypatch):
    write_config(home / "seller", network__nostr_relays=None)
    monkeypatch.setenv("KUBERBOLT_RELAYS", "wss://a.test, wss://b.test")
    assert load_config("seller").relays == ["wss://a.test", "wss://b.test"]


def test_packaged_template_matches_canonical_schema():
    repo = Path(__file__).resolve().parents[3]
    packaged = Path(__file__).resolve().parents[1] / "nostr_sdk_wrapper" / "templates" / "agent.example.yaml"
    assert packaged.read_text() == (repo / "kuberbolt-config" / "agent.example.yaml").read_text()
