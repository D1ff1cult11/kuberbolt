"""
Agent identity: keypair generation, persistence to disk, and kind:0 profile
publishing.

Tested against nostr-sdk 0.45.0 -- see the module-level note in
discovery.py/handshake.py about API changes from earlier versions used in
this project. In this version:
  - There's no `NostrSigner.keys(keys)` wrapper anymore -- `Keys` objects
    are accepted directly anywhere a signer is expected.
  - `EventBuilder.sign_with_keys(keys)` is gone -- use `.finalize(keys)`.
"""

from __future__ import annotations

import json
import os
import re
from importlib import resources
from pathlib import Path

from nostr_sdk import Client, Event, Keys, Metadata, MetadataRecord, SecretKey

from .config import ROLES, ConfigError, agent_dir


def generate_identity() -> Keys:
    """Generate a brand-new secp256k1 keypair for an agent."""
    return Keys.generate()


def save_identity(keys: Keys, path: str | Path) -> None:
    """Persist an identity to disk as JSON. Stores the secret key in both
    hex and bech32 (nsec) form for convenience, plus the public key (hex
    and npub) so the file is human-inspectable without needing to re-derive
    anything.

    SECURITY NOTE: this file contains a real secret key in plaintext. Keep
    it out of version control (add it to .gitignore) and restrict its file
    permissions -- this function sets it to 0600 (owner read/write only)
    right after writing.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "secret_key_hex": keys.secret_key().to_hex(),
        "secret_key_bech32": keys.secret_key().to_bech32(),
        "public_key_hex": keys.public_key().to_hex(),
        "public_key_bech32": keys.public_key().to_bech32(),
    }
    # Create with 0600 so the key is never readable by others, even briefly.
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(data, f, indent=2)

    os.chmod(path, 0o600)


def load_identity(path: str | Path) -> Keys:
    """Load a previously saved identity from disk."""
    path = Path(path)
    with open(path) as f:
        data = json.load(f)
    secret_key = SecretKey.parse(data["secret_key_hex"])
    return Keys(secret_key)


async def publish_profile(client: Client, keys: Keys, name: str | None = None,
                          about: str | None = None, picture: str | None = None,
                          **extra_fields) -> Event:
    """Publish a kind:0 profile (NIP-01 metadata) for this agent. `client`
    must already be connected to at least one relay. `**extra_fields` maps
    to any other MetadataRecord field (website, nip05, lud16, etc.)."""
    record = MetadataRecord(name=name, about=about,
                            picture=picture, **extra_fields)
    metadata = Metadata.from_record(record)
    event = metadata.into_event_builder().finalize(keys)
    await client.send_event(event)
    return event


def init_agent(name: str, role: str, home: str | Path | None = None,
               nsec: str | None = None) -> Path:
    """Create $KUBERBOLT_HOME/<name>/ (mode 0700) with identity.json (0600)
    and a config.yaml skeleton copied from the packaged schema template
    (kuberbolt-config/agent.example.yaml) with agent.name/role filled in.

    Idempotent: an existing identity.json is never overwritten. If `nsec`
    is given, that key is imported instead of generating a new one; passing
    an nsec that differs from an existing identity is an error.

    Returns the agent directory. This is the single owner of Nostr key
    generation for an agent; the Go financial pod only loads identity.json.
    """
    if role not in ROLES:
        raise ConfigError(f"role must be one of {ROLES}, got {role!r}")
    directory = agent_dir(name, home)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)

    identity_path = directory / "identity.json"
    if identity_path.exists():
        existing = load_identity(identity_path).secret_key().to_hex()
        if nsec is not None and SecretKey.parse(nsec).to_hex() != existing:
            raise ConfigError(f"{identity_path} already holds a different key; refusing to overwrite it")
    else:
        save_identity(Keys(SecretKey.parse(nsec)) if nsec else generate_identity(), identity_path)

    config_path = directory / "config.yaml"
    if not config_path.exists():
        text = resources.files(__package__).joinpath("templates/agent.example.yaml").read_text()
        for key, value in (("name", directory.name), ("role", role)):
            text = re.sub(rf'^  {key}: ""', lambda _: f"  {key}: {json.dumps(value)}", text, count=1, flags=re.M)
        config_path.write_text(text)
    return directory
