"""KuberboltAgent.serve_endpoint_requests (seller-side resolver loop) and
feedback event building. Ported from the deleted root tests/."""

import asyncio
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nostr_sdk import Keys, PublicKey

from nostr_sdk_wrapper.agent import KuberboltAgent
from nostr_sdk_wrapper.feedback import publish_feedback

SENDER = "sender_pubkey_123"


def _event(event_id, author=SENDER):
    ev = MagicMock()
    ev.id.return_value.to_hex.return_value = event_id
    ev.author.return_value.to_hex.return_value = author
    return ev


@pytest.fixture
def agent():
    a = KuberboltAgent(MagicMock(), MagicMock())
    a.send_handshake = AsyncMock()
    return a


def _serve(agent, db_path, events, payload, rounds=1, **kwargs):
    """Run the loop for `rounds` fetches, each returning `events`."""
    stop = asyncio.Event()
    calls = 0

    async def fetch(*args, **kw):
        nonlocal calls
        calls += 1
        if calls >= rounds:
            stop.set()
        return events

    decrypt = {"side_effect": payload} if isinstance(payload, Exception) else {"return_value": payload}
    with patch("nostr_sdk_wrapper.handshake.fetch_handshake_events", side_effect=fetch), \
         patch("nostr_sdk_wrapper.handshake.decrypt_event", **decrypt):
        asyncio.run(agent.serve_endpoint_requests(
            host="10.0.0.5", port=6001, poll_interval=1, db_path=db_path, stop_event=stop, **kwargs))


def test_replies_and_records_request(agent, tmp_path):
    db = tmp_path / "ledger.db"
    _serve(agent, db, [_event("ev1")], {"action": "resolve_endpoint", "job_id": "job-1"})
    agent.send_handshake.assert_awaited_once_with(SENDER, {"job_id": "job-1", "host": "10.0.0.5", "port": 6001})
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT event_id, sender_pubkey, job_id FROM seen_requests").fetchone()
    assert row == ("ev1", SENDER, "job-1")


def test_deduplicates_seen_events(agent, tmp_path):
    _serve(agent, tmp_path / "ledger.db", [_event("dup")], {"action": "resolve_endpoint", "job_id": "j"}, rounds=2)
    assert agent.send_handshake.await_count == 1


def test_ignores_missing_job_id(agent, tmp_path):
    _serve(agent, tmp_path / "ledger.db", [_event("ev")], {"action": "resolve_endpoint"})
    agent.send_handshake.assert_not_called()


def test_ignores_sender_not_allowed(agent, tmp_path):
    _serve(agent, tmp_path / "ledger.db", [_event("ev")], {"action": "resolve_endpoint", "job_id": "j"},
           allowed_pubkeys=["someone_else"])
    agent.send_handshake.assert_not_called()


def test_ignores_undecryptable_event(agent, tmp_path):
    _serve(agent, tmp_path / "ledger.db", [_event("ev")], ValueError("bad signature"))
    agent.send_handshake.assert_not_called()


def test_publish_feedback_tags_job_id():
    client = AsyncMock()
    event = asyncio.run(publish_feedback(
        client=client, reviewer_keys=Keys.generate(), counterparty_pubkey=PublicKey.parse("c" * 64),
        job_id="any-job-id", feedback_text="Great service", rating=5))
    client.send_event.assert_awaited_once_with(event)
    assert ["e", "any-job-id"] in [t.to_vec() for t in event.tags()]
