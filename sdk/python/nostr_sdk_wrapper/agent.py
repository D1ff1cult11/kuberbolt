"""
KuberboltAgent -- the SDK entry point. Wraps identity management, relay
connection, discovery, and handshake into one object so a calling agent
never needs to touch the command line or know about the underlying
nostr-sdk plumbing.

Typical usage:

    from nostr_sdk_wrapper import KuberboltAgent, load_config

    cfg = load_config("my-agent")          # $KUBERBOLT_HOME/my-agent/config.yaml
    agent = await KuberboltAgent.from_config(cfg)

    providers = await agent.discover(category)
    if providers:
        reply = await agent.request_endpoint(providers[0]["nostr_pubkey"])

    await agent.disconnect()
"""

from __future__ import annotations
from .config import ConfigError, KuberboltConfig
from .discovery import TaggedEvent
from . import discovery, feedback, handshake, identity
from nostr_sdk import (
    Client,
    Event,
    EventBuilder,
    Keys,
    Kind,
    PublicKey,
    RelayStatus,
    RelayUrl,
    Tag,
)

import asyncio
import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger("kuberbolt.nostr_sdk_wrapper.agent")


class AgentNotRegisteredError(ValueError):
    def __init__(self, pubkey: str):
        self.pubkey = pubkey
        super().__init__(
            f"You are not registered (no profile found for {pubkey})")


class KuberboltAgent:
    """A Nostr-backed agent identity, already connected to relays, with
    discovery and handshake methods attached. Construct via `from_config()`
    (or `from_keys()`), not `__init__()` directly -- relay
    connection is async. `cfg` supplies default timeouts when present."""

    def __init__(self, keys: Keys, client: Client, cfg: KuberboltConfig | None = None):
        self.keys = keys
        self.client = client
        self.cfg = cfg

    def _timeout(self, value: float | None, setting: str) -> float:
        """`value` if given, else network.<setting> from the agent's config."""
        if value is not None:
            return value
        if self.cfg is None:
            raise ValueError(f"timeout_secs is required when the agent has no config (network.{setting})")
        return getattr(self.cfg, setting)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    @classmethod
    async def from_config(cls, cfg: "KuberboltConfig") -> "KuberboltAgent":
        """Primary entry point: load the identity at cfg.identity_path
        (it must already exist; see identity.init_agent) and connect to
        cfg.relays, waiting cfg.relay_connect_wait_sec. Does not publish
        anything; call register() for that."""
        if not cfg.identity_path.exists():
            raise ConfigError(f"{cfg.identity_path} not found: run `kuberbolt init --name {cfg.name}`")
        agent = await cls.from_keys(identity.load_identity(cfg.identity_path), cfg.relays,
                                    cfg.relay_connect_wait_sec)
        agent.cfg = cfg
        return agent

    @classmethod
    async def from_keys(cls, keys: Keys, relay_urls: list[str],
                        connect_wait_secs: float) -> "KuberboltAgent":
        """Construct a KuberboltAgent from an already-loaded Keys object,
        connecting to the given relays without any disk I/O."""
        client = Client()
        for url in relay_urls:
            await client.add_relay(RelayUrl.parse(url))
        await client.connect()
        await asyncio.sleep(connect_wait_secs)
        return cls(keys, client)

    async def connection_report(self) -> dict[str, str]:
        """Returns {relay_url: status_string} -- useful for a caller to
        check how many relays actually connected before relying on
        discovery/handshake results."""
        relays = await self.client.relays()
        return {str(url): str(relay.status()) for url, relay in relays.items()}

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

    async def register(self, role: Literal["client", "merchant"], display_name: str,
                       about: str | None = None,
                       lightning_address: str | None = None,
                       service: dict | None = None,
                       picture_url: str | None = None) -> dict:
        """Register profile and optionally service listing (if merchant role)."""
        profile_event = await self.publish_profile(
            name=display_name, about=about, picture=picture_url, lud16=lightning_address
        )
        listing_event = None
        if role == "merchant":
            if service is None:
                raise ValueError("service info required for merchant role")
            payload = {
                "service_name": service["service_name"],
                "service_description": service["service_description"],
                "price_sats": service["price_sats"],
                "price_unit": service["price_unit"],
            }
            content = json.dumps(payload)
            category_tag = f"kuberbolt/{service['category']}" if not service["category"].startswith(
                "kuberbolt/") else service["category"]
            listing_event = (
                EventBuilder(Kind(discovery.KIND_SERVICE_LISTING), content)
                .tags([
                    Tag.hashtag(discovery.normalize_tag(category_tag)),
                    Tag.identifier(self.pubkey_hex),
                ])
                .finalize(self.keys)
            )
            await self.client.send_event(listing_event)

        return {
            "nostr_pubkey": self.pubkey_hex,
            "profile_event_id": profile_event.id().to_hex(),
            "listing_event_id": listing_event.id().to_hex() if listing_event is not None else None,
        }

    async def register_from_config(self) -> dict:
        """register() using the agent block and (for merchants) the single
        service from this agent's config. One listing per agent: the listing
        is replaceable by pubkey, so a second service would overwrite it."""
        cfg = self.cfg
        if cfg is None:
            raise ValueError("register_from_config needs an agent built with from_config()")
        service = None
        if cfg.role == "merchant":
            if len(cfg.services) != 1:
                raise ConfigError(f"{cfg.agent_dir / 'config.yaml'}: exactly one entry in services is supported")
            s = cfg.services[0]
            service = {
                "service_name": s.name,
                "service_description": s.description,
                "price_sats": s.price_sats,
                "price_unit": s.price_unit,
                "category": s.category,
            }
        return await self.register(cfg.role, cfg.display_name, about=cfg.about,
                                   lightning_address=cfg.lightning_address, service=service,
                                   picture_url=cfg.picture_url)
    # ------------------------------------------------------------------
    # Update profile
    # ------------------------------------------------------------------

    async def update_agent(self, updates: list[dict], timeout_secs: int | None = None) -> dict:
        timeout_secs = self._timeout(timeout_secs, "discovery_timeout_sec")
        existing = await discovery.fetch_existing_profile(self.client, self.pubkey_hex, timeout_secs)
        if existing is None:
            raise AgentNotRegisteredError(self.pubkey_hex)

        current_profile = json.loads(existing.content())
        changed = {update["field"]: update["value"] for update in updates}
        profile_fields = {"display_name", "about",
                          "picture_url", "lightning_address"}
        listing_fields = {"service_name",
                          "service_description", "price_sats", "price_unit"}

        profile_event_id = None
        if changed.keys() & profile_fields:
            profile_event = await self.publish_profile(
                name=changed.get("display_name", current_profile.get("name")),
                about=changed.get("about", current_profile.get("about")),
                picture=changed.get(
                    "picture_url", current_profile.get("picture")),
                lud16=changed.get("lightning_address",
                                  current_profile.get("lud16")),
            )
            profile_event_id = profile_event.id().to_hex()

        listing_event_id = None
        if changed.keys() & listing_fields:
            existing_listing = await discovery.fetch_existing_listing(self.client, self.pubkey_hex, timeout_secs)
            if existing_listing is None:
                raise ValueError(
                    "No existing service listing to update - register as merchant first")
            current_listing = json.loads(existing_listing.content())
            merged_listing = {
                **current_listing,
                **{field: changed[field] for field in listing_fields if field in changed},
            }
            listing_event = (
                EventBuilder(Kind(discovery.KIND_SERVICE_LISTING),
                             json.dumps(merged_listing))
                .tags(existing_listing.tags())
                .finalize(self.keys)
            )
            await self.client.send_event(listing_event)
            listing_event_id = listing_event.id().to_hex()

        return {
            "updated_fields": list(changed.keys()),
            "profile_event_id": profile_event_id,
            "listing_event_id": listing_event_id,
        }

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    async def find_providers(self, tag: str, kinds: list[int] | None = None,
                             limit: int = 50, timeout_secs: int | None = None) -> list[TaggedEvent]:
        """Find service providers self-tagged with `tag` (normalized
        automatically -- 'Video_Analysis' and 'video-analysis' match the
        same providers)."""
        return await discovery.find_by_hashtag(
            self.client, tag, kinds=kinds, limit=limit,
            timeout_secs=self._timeout(timeout_secs, "discovery_timeout_sec")
        )

    async def discover(self, category: str, price_max: int | None = None,
                       limit: int = 50, timeout_secs: int | None = None) -> list[dict]:
        """Discover service listings under `category` with optional price filtering."""
        timeout_secs = self._timeout(timeout_secs, "discovery_timeout_sec")
        category_tag = f"kuberbolt/{category}" if not category.startswith(
            "kuberbolt/") else category
        results = await discovery.find_by_hashtag(
            self.client, category_tag, kinds=[discovery.KIND_SERVICE_LISTING],
            limit=limit, timeout_secs=timeout_secs
        )

        discovered = []
        for result in results:
            try:
                data = json.loads(result.content)
                if not isinstance(data, dict):
                    continue
            except Exception:
                continue

            price_sats = data.get("price_sats")
            if price_max is not None and price_sats is not None and price_sats > price_max:
                continue

            # fetch_profile per-result is N+1 relay calls, future optimization = batched author filter, don't build now
            try:
                author_pk = PublicKey.parse(result.author_pubkey)
                profile = await discovery.fetch_profile(self.client, author_pk, timeout_secs)
            except Exception:
                profile = None

            discovered.append({
                "provider_id": result.author_pubkey,
                "nostr_pubkey": result.author_pubkey,
                "name": profile.get("name") if profile else None,
                "category": category,
                "price_sats": price_sats,
                "price_unit": data.get("price_unit"),
                "service_name": data.get("service_name"),
                "service_description": data.get("service_description"),
                "listing_event_id": result.event_id,
                "created_at": result.created_at,
            })

        discovered.sort(key=lambda x: x["created_at"], reverse=True)
        return discovered

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

    async def request_endpoint(self, provider_pubkey: str, job_id: str | None = None,
                               timeout_secs: int | None = None) -> dict | None:
        """Buyer side of the endpoint handshake: send a NIP-44
        {"action": "resolve_endpoint", "job_id": ...} to the provider and
        poll for the matching reply. `job_id` defaults to a fresh uuid4.
        `timeout_secs` defaults to the config's handshake_timeout_sec.

        Returns the provider's reply {"job_id", "host", "port"}, or None if
        no reply arrived in time. Replaces api/routers/requests.py."""
        timeout_secs = self._timeout(timeout_secs, "handshake_timeout_sec")
        job_id = job_id or str(uuid.uuid4())
        await self.send_handshake(provider_pubkey, {"action": "resolve_endpoint", "job_id": job_id})
        deadline = time.monotonic() + timeout_secs
        while time.monotonic() < deadline:
            remaining = max(1, int(deadline - time.monotonic()))
            replies = await self.fetch_handshake_replies(timeout_secs=min(3, remaining))
            for reply in replies:
                if reply.get("job_id") == job_id and "host" in reply:
                    return reply
            await asyncio.sleep(0.25)
        return None

    async def fetch_handshake_replies(self, timeout_secs: int) -> list[dict]:
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

    async def publish_feedback(
        self,
        counterparty_pubkey: str | PublicKey,
        job_id: str,
        feedback_text: str,
        rating: int,
    ) -> Event:
        """Publish signed kind:7000 feedback for a completed job."""
        if isinstance(counterparty_pubkey, str):
            counterparty_pubkey = PublicKey.parse(counterparty_pubkey)
        return await feedback.publish_feedback(
            self.client,
            self.keys,
            counterparty_pubkey,
            job_id,
            feedback_text,
            rating,
        )

    # ------------------------------------------------------------------
    # Automated Endpoint Resolution (Provider Daemon)
    # ------------------------------------------------------------------

    async def serve_endpoint_requests(
        self,
        host: str,
        port: int,
        poll_interval: int,
        db_path: str | Path,
        allowed_pubkeys: list[str] | None = None,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """Background listener/server loop for Provider Agents.

        Polls for NIP-44 encrypted `resolve_endpoint` handshake requests, records
        processed event IDs in SQLite (`seen_requests` table) before replying to
        prevent duplicate replies/race conditions, and responds with the gRPC
        `host` and `port`.
        """
        conn = sqlite3.connect(db_path)
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS seen_requests (
                    event_id        TEXT PRIMARY KEY,
                    sender_pubkey   TEXT NOT NULL,
                    job_id          TEXT,
                    replied_at      TIMESTAMP NOT NULL
                );
            """)

        consecutive_errors = 0

        try:
            while stop_event is None or not stop_event.is_set():
                try:
                    events = await handshake.fetch_handshake_events(
                        self.client, self.keys.public_key(), timeout_secs=poll_interval
                    )
                    consecutive_errors = 0
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    consecutive_errors += 1
                    backoff_secs = min(
                        poll_interval * (2 ** (consecutive_errors - 1)), 60)
                    logger.error(
                        "Error fetching handshake events (attempt %d): %s. Backing off for %ds.",
                        consecutive_errors,
                        e,
                        backoff_secs,
                    )
                    await asyncio.sleep(backoff_secs)
                    continue

                for ev in events:
                    event_id = ev.id().to_hex()

                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT 1 FROM seen_requests WHERE event_id = ?", (event_id,))
                    if cursor.fetchone() is not None:
                        continue

                    try:
                        payload = handshake.decrypt_event(self.keys, ev)
                        if not isinstance(payload, dict):
                            continue
                    except Exception as e:
                        logger.warning(
                            "Failed to decrypt event %s: %s", event_id, e)
                        continue

                    if payload.get("action") != "resolve_endpoint":
                        continue

                    job_id = payload.get("job_id")
                    if not job_id:
                        logger.warning(
                            "Missing job_id in resolve_endpoint request %s", event_id)
                        continue

                    sender_pubkey = ev.author().to_hex()
                    if allowed_pubkeys is not None and sender_pubkey not in allowed_pubkeys:
                        logger.warning(
                            "Sender %s not in allowed_pubkeys list for event %s", sender_pubkey, event_id
                        )
                        continue

                    # Send handshake response with host and port
                    reply_payload = {
                        "job_id": job_id,
                        "host": host,
                        "port": port,
                    }
                    try:
                        await self.send_handshake(sender_pubkey, reply_payload)
                        now_iso = datetime.now(timezone.utc).isoformat()
                        with conn:
                            conn.execute(
                                "INSERT INTO seen_requests (event_id, sender_pubkey, job_id, replied_at) VALUES (?, ?, ?, ?)",
                                (event_id, sender_pubkey, job_id, now_iso),
                            )
                        logger.info(
                            "Successfully replied to resolve_endpoint for job_id %s to %s",
                            job_id,
                            sender_pubkey,
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to send handshake reply for job_id %s to %s: %s",
                            job_id,
                            sender_pubkey,
                            e,
                        )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    async def disconnect(self):
        await self.client.disconnect()
