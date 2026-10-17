import asyncio
import base64
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import seller_agent
from nostr_sdk_wrapper.config import ConfigError, KuberboltConfig, ServiceConfig


def make_cfg(**overrides) -> KuberboltConfig:
    fields = dict(
        agent_dir=Path("/tmp/kb-test/seller"),
        name="seller",
        role="merchant",
        identity_path=Path("/tmp/kb-test/seller/identity.json"),
        ledger_path=Path("/tmp/kb-test/seller/ledger.db"),
        display_name="Test Seller",
        about=None,
        picture_url=None,
        lightning_address=None,
        services=[ServiceConfig("summarize", "text", "Summaries", 100_000, "per_request", 7)],
        relays=["wss://relay.test"],
        relay_connect_wait_sec=1.0,
        handshake_timeout_sec=5,
        discovery_timeout_sec=5,
        endpoint_poll_sec=4,
        grpc_port=7001,
        public_host="10.1.2.3",
        pod_addr=None,
        brain={"url": "http://10.1.2.3:9001", "listen_host": "127.0.0.9", "listen_port": 9001,
               "llm_model": "test-model"},
    )
    fields.update(overrides)
    return KuberboltConfig(**fields)


@pytest.fixture
def client():
    seller_agent.app.state.cfg = make_cfg()
    return TestClient(seller_agent.app)


def compute(client, service_kind="summarize", text="Some text to summarize."):
    job = base64.b64encode(json.dumps({"text": text}).encode()).decode()
    resp = client.post("/compute", json={"service_kind": service_kind, "job_spec_base64": job})
    assert resp.status_code == 200
    return resp.json()


def test_health_reports_config_values(client):
    data = client.get("/health").json()
    assert data["public_host"] == "10.1.2.3"
    assert data["grpc_port"] == 7001
    assert data["llm_model"] == "test-model"


def test_compute_returns_error_when_llm_fails(client):
    with patch.object(seller_agent, "summarize_text", AsyncMock(side_effect=RuntimeError("boom"))):
        data = compute(client)
    assert data["output_data_base64"] == ""
    assert "boom" in data["error"]


def test_compute_uses_configured_model_and_timeout(client):
    mock = AsyncMock(return_value="short summary")
    with patch.object(seller_agent, "summarize_text", mock):
        data = compute(client)
    assert data["error"] == ""
    out = json.loads(base64.b64decode(data["output_data_base64"]))
    assert out["summary"] == "short summary"
    mock.assert_awaited_once_with("Some text to summarize.", "test-model", 7)


def test_compute_rejects_unconfigured_service(client):
    with patch.object(seller_agent, "summarize_text", AsyncMock()) as mock:
        data = compute(client, service_kind="something-else")
    assert data["error"]
    mock.assert_not_awaited()


def test_summarize_text_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="GOOGLE_API_KEY"):
        asyncio.run(seller_agent.summarize_text("hi", "test-model", 1))


def test_main_wires_config_values(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    cfg = make_cfg()
    agent = MagicMock()
    agent.register_from_config = AsyncMock(return_value={"listing_event_id": "abc"})
    agent.serve_endpoint_requests = AsyncMock()
    agent.disconnect = AsyncMock()
    from_config = AsyncMock(return_value=agent)
    server = MagicMock()
    server.serve = AsyncMock()

    with patch.object(seller_agent, "load_config", return_value=cfg), \
            patch.object(seller_agent.KuberboltAgent, "from_config", from_config), \
            patch.object(seller_agent.uvicorn, "Config") as uv_config, \
            patch.object(seller_agent.uvicorn, "Server", return_value=server):
        asyncio.run(seller_agent.main())

    from_config.assert_awaited_once_with(cfg)
    agent.register_from_config.assert_awaited_once()
    assert uv_config.call_args.kwargs["host"] == "127.0.0.9"
    assert uv_config.call_args.kwargs["port"] == 9001
    kwargs = agent.serve_endpoint_requests.call_args.kwargs
    assert (kwargs["host"], kwargs["port"], kwargs["poll_interval"], kwargs["db_path"]) == (
        "10.1.2.3", 7001, 4, cfg.ledger_path)
    agent.disconnect.assert_awaited_once()


def test_main_fails_loudly_without_public_host(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    with patch.object(seller_agent, "load_config", return_value=make_cfg(public_host=None)), \
            patch.object(seller_agent.KuberboltAgent, "from_config", AsyncMock()) as from_config:
        with pytest.raises(ConfigError, match="network.public_host"):
            asyncio.run(seller_agent.main())
    from_config.assert_not_awaited()
