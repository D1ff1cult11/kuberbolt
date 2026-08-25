"""
Shared fixtures for the Kuberbolt API test suite.

All tests run against a fully-mocked KuberboltAgent so no real relay
connections are ever attempted.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixed test data
# ---------------------------------------------------------------------------

FAKE_PUBKEY = "a" * 64
FAKE_PRIVKEY = "b" * 64
FAKE_PROFILE_EVENT_ID = "c" * 64
FAKE_LISTING_EVENT_ID = "d" * 64

SAMPLE_PROVIDERS = [
    {
        "provider_id": "provider_1",
        "nostr_pubkey": "pub1",
        "name": "AI Text Bot",
        "picture_url": None,
        "category": "ai_text",
        "price_sats": 50,
        "price_unit": "per_request",
        "service_name": "Text Gen",
        "service_description": "Generates text",
        "listing_event_id": "listing1",
    },
    {
        "provider_id": "provider_2",
        "nostr_pubkey": "pub2",
        "name": "Video Bot",
        "picture_url": None,
        "category": "video",
        "price_sats": 200,
        "price_unit": "per_minute",
        "service_name": "Video Analysis",
        "service_description": "Analyses video",
        "listing_event_id": "listing2",
    },
    {
        "provider_id": "provider_3",
        "nostr_pubkey": "pub3",
        "name": "Budget Text",
        "picture_url": None,
        "category": "ai_text",
        "price_sats": 10,
        "price_unit": "flat",
        "service_name": "Cheap Text",
        "service_description": "Basic text",
        "listing_event_id": "listing3",
    },
]


# ---------------------------------------------------------------------------
# Mock KuberboltAgent factory
# ---------------------------------------------------------------------------

def _build_mock_agent() -> MagicMock:
    """Return a MagicMock that quacks like KuberboltAgent."""
    agent = MagicMock()
    agent.pubkey_hex = FAKE_PUBKEY

    # register() -> dict
    agent.register = AsyncMock(return_value={
        "nostr_pubkey": FAKE_PUBKEY,
        "nostr_privkey": FAKE_PRIVKEY,
        "profile_event_id": FAKE_PROFILE_EVENT_ID,
        "listing_event_id": FAKE_LISTING_EVENT_ID,
    })

    # publish_profile() -> mock event with .id().to_hex()
    mock_event = MagicMock()
    mock_event.id.return_value.to_hex.return_value = FAKE_PROFILE_EVENT_ID
    agent.publish_profile = AsyncMock(return_value=mock_event)

    # disconnect()
    agent.disconnect = AsyncMock()

    # discover() — the discovery agent uses this
    agent.discover = AsyncMock(return_value=SAMPLE_PROVIDERS)

    # handshake methods
    mock_handshake_event = MagicMock()
    mock_handshake_event.id.return_value.to_hex.return_value = "handshake_event_hex"
    agent.send_handshake = AsyncMock(return_value=mock_handshake_event)
    agent.fetch_handshake_replies = AsyncMock(return_value=[{"result": "ok"}])

    return agent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_agent():
    """Provide a fresh mock KuberboltAgent for each test."""
    return _build_mock_agent()


@pytest.fixture()
def client(mock_agent):
    """
    TestClient wired to the real FastAPI app, with KuberboltAgent mocked at
    every import boundary so no network access occurs.
    """
    # Patch KuberboltAgent.create and from_existing_key at the agents router boundary
    with (
        patch("api.routers.agents.KuberboltAgent") as AgentClsAgents,
        patch("api.routers.requests.KuberboltAgent") as AgentClsRequests,
        patch("api.routers.requests.Keys") as MockKeys,
        patch("api.routers.requests.SecretKey") as MockSecretKey,
        patch("api.routers.providers.get_discovery_agent", new_callable=AsyncMock) as mock_discovery,
    ):
        # agents router: KuberboltAgent.create() -> mock_agent
        AgentClsAgents.create = AsyncMock(return_value=mock_agent)
        AgentClsAgents.from_existing_key = AsyncMock(return_value=mock_agent)

        # requests router: KuberboltAgent.from_keys() -> mock_agent
        AgentClsRequests.from_keys = AsyncMock(return_value=mock_agent)

        # Keys / SecretKey mocking for requests router
        mock_keys_instance = MagicMock()
        MockKeys.return_value = mock_keys_instance
        MockSecretKey.parse.return_value = MagicMock()

        # discovery agent
        mock_discovery.return_value = mock_agent

        from api.main import app
        yield TestClient(app, raise_server_exceptions=False)
