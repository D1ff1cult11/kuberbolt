import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nostr_sdk_wrapper.agent import KuberboltAgent
from nostr_sdk_wrapper.config import ConfigError, load_config
from nostr_sdk_wrapper.identity import init_agent, load_identity

PROVIDER = "b" * 64


def _agent(cfg=None):
    agent = KuberboltAgent(MagicMock(), MagicMock(), cfg)
    agent.send_handshake = AsyncMock()
    return agent


@pytest.fixture
def cfg(home, write_config):
    init_agent("seller", "merchant")
    write_config(home / "seller")
    return load_config("seller")


def test_request_endpoint_returns_matching_reply(cfg):
    agent = _agent(cfg)
    reply = {"job_id": "job-1", "host": "10.0.0.5", "port": 6001}
    agent.fetch_handshake_replies = AsyncMock(return_value=[{"job_id": "other", "host": "x", "port": 1}, reply])

    assert asyncio.run(agent.request_endpoint(PROVIDER, job_id="job-1")) == reply
    agent.send_handshake.assert_awaited_once_with(PROVIDER, {"action": "resolve_endpoint", "job_id": "job-1"})


def test_request_endpoint_generates_job_id(cfg):
    agent = _agent(cfg)
    seen = {}

    async def send(pubkey, payload):
        seen.update(payload)

    async def replies(timeout_secs):
        return [{"job_id": seen["job_id"], "host": "h", "port": 1}]

    agent.send_handshake = send
    agent.fetch_handshake_replies = replies
    assert asyncio.run(agent.request_endpoint(PROVIDER))["job_id"] == seen["job_id"]


def test_request_endpoint_timeout_returns_none(cfg):
    agent = _agent(cfg)
    agent.fetch_handshake_replies = AsyncMock(return_value=[{"job_id": "other", "host": "x", "port": 1}])
    assert asyncio.run(agent.request_endpoint(PROVIDER, job_id="job-1", timeout_secs=1)) is None


def test_request_endpoint_without_config_or_timeout_raises():
    with pytest.raises(ValueError, match="handshake_timeout_sec"):
        asyncio.run(_agent().request_endpoint(PROVIDER))


def test_from_config_loads_identity_and_connects(cfg):
    client = MagicMock(add_relay=AsyncMock(), connect=AsyncMock())
    with patch("nostr_sdk_wrapper.agent.Client", return_value=client):
        agent = asyncio.run(KuberboltAgent.from_config(cfg))
    assert agent.cfg is cfg
    assert agent.pubkey_hex == load_identity(cfg.identity_path).public_key().to_hex()
    assert client.add_relay.await_count == len(cfg.relays)
    client.connect.assert_awaited_once()


def test_from_config_requires_identity(home, write_config):
    write_config(home / "seller")
    with pytest.raises(ConfigError, match="kuberbolt init"):
        asyncio.run(KuberboltAgent.from_config(load_config("seller")))


def test_register_from_config_merchant(cfg):
    agent = _agent(cfg)
    agent.register = AsyncMock(return_value={})
    asyncio.run(agent.register_from_config())
    agent.register.assert_awaited_once_with(
        "merchant", "Test Seller", about=None, lightning_address=None, picture_url=None,
        service={
            "service_name": "text-summarization",
            "service_description": "Summarizes text",
            "price_sats": 50,
            "price_unit": "per_request",
            "category": "ai-text",
        },
    )
