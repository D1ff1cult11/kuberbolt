import asyncio
import base64
import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import buyer_agent
from nostr_sdk_wrapper.config import ConfigError, KuberboltConfig


def make_cfg(**overrides) -> KuberboltConfig:
    fields = dict(
        agent_dir=Path("/tmp/kb-test/buyer"),
        name="buyer",
        role="client",
        identity_path=Path("/tmp/kb-test/buyer/identity.json"),
        ledger_path=Path("/tmp/kb-test/buyer/ledger.db"),
        display_name="Test Buyer",
        about=None,
        picture_url=None,
        lightning_address=None,
        services=[],
        relays=["wss://relay.test"],
        relay_connect_wait_sec=1.0,
        handshake_timeout_sec=5,
        discovery_timeout_sec=5,
        endpoint_poll_sec=None,
        grpc_port=7002,
        public_host=None,
        pod_addr="127.0.0.9:7002",
        brain={"llm_model": "test-model"},
    )
    fields.update(overrides)
    return KuberboltConfig(**fields)


def make_agent() -> MagicMock:
    agent = MagicMock()
    agent.discover = AsyncMock(return_value=[{"nostr_pubkey": "pk", "service_name": "summarize"}])
    agent.request_endpoint = AsyncMock(return_value={"job_id": "j1", "host": "10.0.0.5", "port": 7001})
    event = MagicMock()
    event.id.return_value.to_hex.return_value = "ev1"
    agent.publish_feedback = AsyncMock(return_value=event)
    agent.disconnect = AsyncMock()
    return agent


@pytest.fixture
def tools():
    agent = make_agent()
    loop = asyncio.new_event_loop()
    fns = {fn.__name__: fn for fn in buyer_agent.make_tools(agent, "127.0.0.9:7002", loop.run_until_complete)}
    yield agent, fns
    loop.close()


def test_discover_and_request_endpoint_call_sdk(tools):
    agent, fns = tools
    assert fns["discover_providers"]("text") == [{"nostr_pubkey": "pk", "service_name": "summarize"}]
    agent.discover.assert_awaited_once_with("text")
    assert fns["request_endpoint"]("pk")["host"] == "10.0.0.5"
    agent.request_endpoint.assert_awaited_once_with("pk")


def test_request_endpoint_reports_timeout(tools):
    agent, fns = tools
    agent.request_endpoint.return_value = None
    assert "error" in fns["request_endpoint"]("pk")


def test_publish_feedback_calls_sdk(tools):
    agent, fns = tools
    assert fns["publish_feedback"]("pk", "j1", 5, "great") == {"event_id": "ev1"}
    agent.publish_feedback.assert_awaited_once_with("pk", "j1", "great", 5)


def test_call_service_uses_pod_addr_and_service_kind(tools):
    _, fns = tools
    stdout = json.dumps({"outputData": base64.b64encode(b'{"summary": "short"}').decode(), "status": "success"})
    done = subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout)
    with patch.object(buyer_agent.subprocess, "run", return_value=done) as run:
        assert fns["call_service"]("10.0.0.5", 7001, "summarize", "hello") == '{"summary": "short"}'
    cmd = run.call_args.args[0]
    body = json.loads(cmd[cmd.index("-d") + 1])
    assert body["provider_endpoint"] == "10.0.0.5:7001"
    assert body["service_kind"] == "summarize"
    assert cmd[-2] == "127.0.0.9:7002"


@pytest.mark.parametrize("argv", [["buyer_agent"], ["buyer_agent", "  "], ["buyer_agent", "a", "b"]])
def test_main_requires_prompt(argv, capsys):
    with patch.object(buyer_agent, "load_config") as load:
        assert buyer_agent.main(argv) != 0
    load.assert_not_called()
    assert "Usage" in capsys.readouterr().err


@pytest.mark.parametrize("overrides, match", [
    ({"role": "merchant"}, "agent.role"),
    ({"pod_addr": None}, "network.pod_addr"),
    ({"brain": {}}, "brain.llm_model"),
])
def test_main_fails_loudly_on_bad_config(monkeypatch, overrides, match):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    with patch.object(buyer_agent, "load_config", return_value=make_cfg(**overrides)), \
            patch.object(buyer_agent.KuberboltAgent, "from_config", AsyncMock()) as from_config:
        with pytest.raises(ConfigError, match=match):
            buyer_agent.main(["buyer_agent", "prompt"])
    from_config.assert_not_awaited()


def test_main_fails_loudly_without_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with patch.object(buyer_agent, "load_config", return_value=make_cfg()):
        with pytest.raises(ConfigError, match="GOOGLE_API_KEY"):
            buyer_agent.main(["buyer_agent", "prompt"])


def test_main_wires_config_and_disconnects(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    cfg = make_cfg()
    agent = make_agent()
    from_config = AsyncMock(return_value=agent)

    def fake_run_agent(prompt, tool_fns, model, api_key):
        assert (prompt, model, api_key) == ("summarize this", "test-model", "test-key")
        fns = {fn.__name__: fn for fn in tool_fns}
        fns["discover_providers"]("text")  # tools run on the agent's loop
        raise RuntimeError("llm crashed")

    with patch.object(buyer_agent, "load_config", return_value=cfg), \
            patch.object(buyer_agent.KuberboltAgent, "from_config", from_config), \
            patch.object(buyer_agent, "run_agent", side_effect=fake_run_agent):
        with pytest.raises(RuntimeError, match="llm crashed"):
            buyer_agent.main(["buyer_agent", "summarize this"])

    from_config.assert_awaited_once_with(cfg)
    agent.discover.assert_awaited_once_with("text")
    agent.disconnect.assert_awaited_once()
