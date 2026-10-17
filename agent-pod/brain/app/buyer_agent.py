"""
Buyer Agent Brain for Kuberbolt Network.

Usage: python -m app.buyer_agent "<prompt>"

Runs on the buyer's machine, configured entirely by $KUBERBOLT_HOME/<agent>/config.yaml
(agent name from KUBERBOLT_AGENT) plus GOOGLE_API_KEY in the environment. A LangChain
ReAct agent (brain.llm_model) gets four tools:
- discover_providers / request_endpoint / publish_feedback: an in-process KuberboltAgent
  talking directly to Nostr relays.
- call_service: the local Go Financial Pod (network.pod_addr) via grpcurl, which handles
  the L402 payment.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
from typing import Callable

from nostr_sdk_wrapper.agent import KuberboltAgent
from nostr_sdk_wrapper.config import ConfigError, load_config

USAGE = 'Usage: python -m app.buyer_agent "<prompt>"'

REACT_TEMPLATE = '''Answer the following questions as best you can. You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought:{agent_scratchpad}'''


def google_api_key() -> str:
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise ConfigError("GOOGLE_API_KEY must be set in the environment")
    return key


def make_tools(agent: KuberboltAgent, pod_addr: str, run: Callable) -> list[Callable]:
    """Plain sync tool functions. `run` executes a coroutine on the event loop the
    agent was created on (the nostr client must stay on that loop)."""

    def discover_providers(category: str) -> list[dict]:
        """Find service providers by category on the Nostr network."""
        return run(agent.discover(category))

    def request_endpoint(provider_pubkey: str) -> dict:
        """Send a NIP-44 encrypted DM to resolve the provider's private gRPC endpoint.
        Returns {"job_id", "host", "port"}."""
        reply = run(agent.request_endpoint(provider_pubkey))
        if reply is None:
            return {"error": f"no endpoint reply from {provider_pubkey}"}
        return reply

    def call_service(host: str, port: int, service_kind: str, text: str) -> str:
        """Call the seller's Financial Pod via gRPC with L402 payment, routed through the
        buyer's local Financial Pod. `service_kind` is the provider listing's service_name."""
        # grpcurl encodes protobuf bytes fields as base64 in JSON.
        job_spec = base64.b64encode(json.dumps({"text": text}).encode()).decode()
        try:
            result = subprocess.run([
                "grpcurl", "-plaintext", "-d",
                json.dumps({
                    "provider_endpoint": f"{host}:{port}",
                    "service_kind": service_kind,
                    "job_spec": job_spec,
                }),
                pod_addr,
                "kuberbolt.v1.FinancialPodService/CallService",
            ], capture_output=True, text=True, check=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            return f"Failed to call service: {e.stderr}"
        except Exception as e:
            return f"Failed to call service: {e}"

    def publish_feedback(provider_pubkey: str, job_id: str, rating: int, feedback: str) -> dict:
        """Publish signed feedback (Nostr kind 7000) for a completed job."""
        event = run(agent.publish_feedback(provider_pubkey, job_id, feedback, rating))
        return {"event_id": event.id().to_hex()}

    return [discover_providers, request_endpoint, call_service, publish_feedback]


def run_agent(prompt: str, tool_fns: list[Callable], model: str, api_key: str) -> None:
    from langchain.agents import AgentExecutor, create_react_agent
    from langchain.tools import tool
    from langchain_core.prompts import PromptTemplate
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(model=model, google_api_key=api_key)
    tools = [tool(fn) for fn in tool_fns]
    agent = create_react_agent(llm, tools, PromptTemplate.from_template(REACT_TEMPLATE))
    executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

    print(f"Running agent with prompt: {prompt}")
    result = executor.invoke({"input": prompt})
    print(result["output"])


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not argv[1].strip():
        print(USAGE, file=sys.stderr)
        return 2
    cfg = load_config()
    if cfg.role != "client":
        raise ConfigError(f"{cfg.agent_dir / 'config.yaml'}: agent.role must be 'client' for the buyer")
    pod_addr = cfg.require(cfg.pod_addr, "network.pod_addr")
    model = cfg.require(cfg.brain.get("llm_model"), "brain.llm_model")
    api_key = google_api_key()

    loop = asyncio.new_event_loop()
    try:
        agent = loop.run_until_complete(KuberboltAgent.from_config(cfg))
        try:
            run_agent(argv[1], make_tools(agent, pod_addr, loop.run_until_complete), model, api_key)
        finally:
            loop.run_until_complete(agent.disconnect())
    finally:
        loop.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
