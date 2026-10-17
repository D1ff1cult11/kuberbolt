import stat

import pytest
import yaml
from nostr_sdk import Keys

from nostr_sdk_wrapper.config import ConfigError
from nostr_sdk_wrapper.identity import init_agent, load_identity


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_init_creates_dir_identity_and_config(home):
    directory = init_agent("alice", "client")
    assert directory == home / "alice"
    assert _mode(directory) == 0o700
    assert _mode(directory / "identity.json") == 0o600
    cfg = yaml.safe_load((directory / "config.yaml").read_text())
    assert cfg["agent"]["name"] == "alice"
    assert cfg["agent"]["role"] == "client"
    assert cfg["agent"]["identity_file"] == "identity.json"
    assert cfg["network"]["nostr_relays"] == []


def test_init_is_idempotent(home):
    directory = init_agent("alice", "client")
    key = load_identity(directory / "identity.json").secret_key().to_hex()
    (directory / "config.yaml").write_text("edited")
    init_agent("alice", "client")
    assert load_identity(directory / "identity.json").secret_key().to_hex() == key
    assert (directory / "config.yaml").read_text() == "edited"


def test_init_imports_nsec(home):
    keys = Keys.generate()
    nsec = keys.secret_key().to_bech32()
    directory = init_agent("alice", "client", nsec=nsec)
    assert load_identity(directory / "identity.json").public_key().to_hex() == keys.public_key().to_hex()
    init_agent("alice", "client", nsec=nsec)  # same key again is fine


def test_init_rejects_different_nsec(home):
    init_agent("alice", "client")
    with pytest.raises(ConfigError, match="different key"):
        init_agent("alice", "client", nsec=Keys.generate().secret_key().to_bech32())


def test_init_rejects_bad_role(home):
    with pytest.raises(ConfigError, match="role"):
        init_agent("alice", "buyer")


def test_init_explicit_home(tmp_path):
    assert init_agent("bob", "merchant", home=tmp_path / "x") == tmp_path / "x" / "bob"
