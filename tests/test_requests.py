"""Tests for the /api/requests endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock
from tests.conftest import FAKE_PUBKEY, SESSION_TOKEN


# ---------------------------------------------------------------------------
# Unknown agent without a valid token -> 401 Unauthorized
# ---------------------------------------------------------------------------

def test_unregistered_agent_returns_404(client, mock_agent):
    """An unknown public key cannot authenticate with another agent's token."""
    response = client.post("/api/requests", json={
        "agent_pubkey": "unregistered_" + "0" * 52,
        "provider_pubkey": "0" * 64,
        "payload": {"action": "ping"},
        "timeout_seconds": 5,
    }, headers={"Authorization": f"Bearer {SESSION_TOKEN}"})

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Registered agent + mocked reply -> success
# ---------------------------------------------------------------------------

def test_registered_agent_with_reply(client, mock_agent):
    """registered agent + mocked send_handshake/fetch_handshake_replies with a reply -> success."""
    mock_agent.fetch_handshake_replies = AsyncMock(return_value=[{"result": "ok"}])

    response = client.post("/api/requests", json={
        "agent_pubkey": FAKE_PUBKEY,
        "provider_pubkey": "0" * 64,
        "payload": {"action": "ping"},
        "timeout_seconds": 5,
    }, headers={"Authorization": f"Bearer {SESSION_TOKEN}"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["result"] is not None
    assert data["result"] == {"result": "ok"}


# ---------------------------------------------------------------------------
# Registered agent + no replies -> no_reply
# ---------------------------------------------------------------------------

def test_registered_agent_no_reply_timeout(client, mock_agent):
    """registered agent + no replies within timeout -> status='no_reply', result=None."""
    mock_agent.fetch_handshake_replies = AsyncMock(return_value=[])

    response = client.post("/api/requests", json={
        "agent_pubkey": FAKE_PUBKEY,
        "provider_pubkey": "0" * 64,
        "payload": {"action": "ping"},
        "timeout_seconds": 1,
    }, headers={"Authorization": f"Bearer {SESSION_TOKEN}"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "no_reply"
    assert data["result"] is None
