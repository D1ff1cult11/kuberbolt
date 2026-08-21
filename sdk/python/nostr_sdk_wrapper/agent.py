"""
KuberboltAgent -- the SDK entry point. Wraps identity management, relay
connection, discovery, and handshake into one object so a calling agent
never needs to touch the command line or know about the underlying
nostr-sdk plumbing.

Typical usage:

    from kuberbolt_nostr.agent import KuberboltAgent

    agent = await KuberboltAgent.create(
        identity_path="buyer_agent_identity.json",
        relay_urls=["wss://relay.damus.io", "wss://nos.lol"],
        profile_name="Kuberbolt Buyer Agent",
        profile_about="Autonomous buyer agent for video analysis jobs.",
    )

    providers = await agent.find_providers("video-analysis")
    if providers:
        event = await agent.send_handshake(
            providers[0].author_pubkey, {"action": "resolve_endpoint"}
        )

    await agent.disconnect()
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from nostr_sdk import Client, Event, Keys, PublicKey, RelayStatus, RelayUrl

from . import discovery, handshake, identity
from .discovery import TaggedEvent


class KuberboltAgent:
    """A Nostr-backed agent identity, already connected to relays, with
    discovery and handshake methods attached. Construct via `create()`,
    not `__init__()` directly -- relay connection is async."""

    def __init__(self, keys: Keys, client: Client):
        self.keys = keys
        self.client = client

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    @classmethod
    async def create(cls, identity_path: str | Path, relay_urls: list[str],
                      profile_name: str | None = None, profile_about: str | None = None,
                      profile_picture: str | None = None,
                      connect_wait_secs: float = 3.0) -> "KuberboltAgent":
        """Load (or generate + persist) an identity, connect to the given
        relays, and optionally publish a kind:0 profile in one call. This
        is the intended entry point -- everything else on this class
        assumes this has already run.

        Set `profile_name` (or any of the profile_* args) to publish/update
        a kind:0 profile as part of setup; leave them all None to skip it
        (e.g. if you've already published a profile in a previous run and
        don't need to republish it every time).
        """
        keys = identity.get_or_create_identity(identity_path)

        client = Client()
        for url in relay_urls:
            await client.add_relay(RelayUrl.parse(url))
        await client.connect()
        await asyncio.sleep(connect_wait_secs)  # let relay handshakes settle

        agent = cls(keys, client)

        if profile_name is not None or profile_about is not None or profile_picture is not None:
            await agent.publish_profile(name=profile_name, about=profile_about, picture=profile_picture)

        return agent

    async def connection_report(self) -> dict[str, str]:
        """Returns {relay_url: status_string} -- useful for a caller to
        check how many relays actually connected before relying on
        discovery/handshake results."""
        relays = await self.client.relays()
        return {url: str(relay.status()) for url, relay in relays.items()}

    async def is_connected(self) -> bool:
        relays = await self.client.relays()
        return any(r.status() == RelayStatus.CONNECTED for r in relays.values())

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def pubkey_hex(self) -> str:
        return self.keys.public_key().to_hex()

    @property
    def npub(self) -> str:
        return self.keys.public_key().to_bech32()

    async def publish_profile(self, name: str | None = None, about: str | None = None,
                               picture: str | None = None, **extra_fields) -> Event:
        """Publish/update this agent's kind:0 profile."""
        return await identity.publish_profile(
            self.client, self.keys, name=name, about=about, picture=picture, **extra_fields
        )

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    async def find_providers(self, tag: str, kinds: list[int] | None = None,
                              limit: int = 50, timeout_secs: int = 8) -> list[TaggedEvent]:
        """Find service providers self-tagged with `tag` (normalized
        automatically -- 'Video_Analysis' and 'video-analysis' match the
        same providers)."""
        return await discovery.find_by_hashtag(
            self.client, tag, kinds=kinds, limit=limit, timeout_secs=timeout_secs
        )

    # ------------------------------------------------------------------
    # Handshake
    # ------------------------------------------------------------------

    async def send_handshake(self, recipient_pubkey: str | PublicKey, payload: dict) -> Event:
        """Send a NIP-44-encrypted handshake message to a provider.
        `recipient_pubkey` can be a hex string (e.g. straight from a
        `TaggedEvent.author_pubkey`) or a `PublicKey` object."""
        if isinstance(recipient_pubkey, str):
            recipient_pubkey = PublicKey.parse(recipient_pubkey)
        return await handshake.send_encrypted_request(
            self.client, self.keys, recipient_pubkey, payload
        )

    async def fetch_handshake_replies(self, timeout_secs: int = 10) -> list[dict]:
        """Fetch and decrypt any handshake-kind events addressed to this
        agent. Returns only the ones that decrypt successfully (skips
        anything that fails signature verification or decryption, rather
        than raising -- a malformed/foreign event shouldn't crash the
        whole batch)."""
        events = await handshake.fetch_handshake_events(
            self.client, self.keys.public_key(), timeout_secs=timeout_secs
        )
        decrypted = []
        for ev in events:
            try:
                decrypted.append(handshake.decrypt_event(self.keys, ev))
            except Exception:
                continue
        return decrypted

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    async def disconnect(self):
        await self.client.disconnect()

