"""
Seller Agent Brain for Kuberbolt Network.

Runs on the seller's machine, configured entirely by $KUBERBOLT_HOME/<agent>/config.yaml
(agent name from KUBERBOLT_AGENT) plus GOOGLE_API_KEY in the environment:
1. On startup, publishes/refreshes its kind:0 profile and kind:31990 listing.
2. Compute Server (FastAPI on brain.listen_host:brain.listen_port): called by the local
   Go Financial Pod once the buyer's HODL payment is locked. Uses Google Gemini
   (brain.llm_model). Any failure is returned as `error`, so the pod cancels the invoice.
3. Endpoint Resolver (NIP-44 listener): answers resolve_endpoint requests from buyers
   with network.public_host and network.grpc_port.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import signal

import httpx
import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel

from nostr_sdk_wrapper.agent import KuberboltAgent
from nostr_sdk_wrapper.config import ConfigError, KuberboltConfig, load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("kuberbolt.seller_agent")

# The provider's fixed API endpoint; the model comes from brain.llm_model.
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# app.state.cfg is set by main() (or by tests) before serving.
app = FastAPI(title="Kuberbolt Seller Brain", version="1.0.0")


class ComputeRequest(BaseModel):
    service_kind: str
    job_spec_base64: str


class ComputeResponse(BaseModel):
    output_data_base64: str
    error: str = ""


def brain_setting(cfg: KuberboltConfig, key: str):
    return cfg.require(cfg.brain.get(key), f"brain.{key}")


def google_api_key() -> str:
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise ConfigError("GOOGLE_API_KEY must be set in the environment")
    return key


async def summarize_text(text: str, model: str, timeout_sec: float) -> str:
    """Summarize text with Gemini. Raises on any failure; there is no fallback."""
    prompt = (
        "You are an AI text summarizer running on the Kuberbolt autonomous agent network.\n"
        "Please provide a clear, high-quality, and concise summary of the following text:\n\n"
        f"{text}"
    )
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        res = await client.post(
            f"{GEMINI_API_BASE}/{model}:generateContent",
            headers={"x-goog-api-key": google_api_key()},  # header, so the key never appears in error URLs
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
    res.raise_for_status()
    return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


@app.get("/health")
async def health(request: Request):
    cfg: KuberboltConfig = request.app.state.cfg
    return {
        "status": "ok",
        "role": "seller_brain",
        "agent": cfg.name,
        "public_host": cfg.public_host,
        "grpc_port": cfg.grpc_port,
        "llm_model": cfg.brain.get("llm_model"),
        "services": [s.name for s in cfg.services],
    }


@app.post("/compute", response_model=ComputeResponse)
async def handle_compute(req: ComputeRequest, request: Request):
    """
    Called by the Go Financial Pod once the buyer's HODL payment is locked.
    A non-empty `error` makes the pod cancel the invoice (buyer refunded) instead of settling.
    """
    cfg: KuberboltConfig = request.app.state.cfg
    logger.info(f"Received compute request for service_kind={req.service_kind}")

    service = next((s for s in cfg.services if s.name == req.service_kind), None)
    if service is None:
        return ComputeResponse(output_data_base64="", error=f"Unknown service kind {req.service_kind!r}")

    try:
        raw_job_spec = base64.b64decode(req.job_spec_base64)
    except Exception as e:
        logger.error(f"Failed to decode base64 job spec: {e}")
        return ComputeResponse(output_data_base64="", error=f"Invalid base64 job spec: {e}")

    try:
        payload = json.loads(raw_job_spec.decode("utf-8"))
        if isinstance(payload, dict):
            text_to_process = payload.get("text") or payload.get("prompt") or payload.get("content") or json.dumps(payload)
        elif isinstance(payload, str):
            text_to_process = payload
        else:
            text_to_process = str(payload)
    except Exception:
        # If not JSON, treat raw bytes as text
        text_to_process = raw_job_spec.decode("utf-8", errors="replace")

    if not text_to_process.strip():
        return ComputeResponse(output_data_base64="", error="No text provided to summarize")

    logger.info(f"Processing compute job (input length: {len(text_to_process)} chars)...")
    try:
        summary = await summarize_text(text_to_process, brain_setting(cfg, "llm_model"), service.timeout_sec)
    except Exception as e:
        logger.error(f"LLM call failed for service_kind={req.service_kind}: {e}")
        return ComputeResponse(output_data_base64="", error=f"LLM call failed: {e}")

    output_payload = {
        "status": "completed",
        "service_kind": req.service_kind,
        "summary": summary,
    }
    output_b64 = base64.b64encode(json.dumps(output_payload, indent=2).encode("utf-8")).decode("utf-8")

    logger.info(f"Compute job completed successfully for service_kind={req.service_kind}")
    return ComputeResponse(output_data_base64=output_b64, error="")


async def main():
    cfg = load_config()
    if cfg.role != "merchant":
        raise ConfigError(f"{cfg.agent_dir / 'config.yaml'}: agent.role must be 'merchant' for the seller")
    listen_host = brain_setting(cfg, "listen_host")
    listen_port = int(brain_setting(cfg, "listen_port"))
    brain_setting(cfg, "llm_model")
    google_api_key()
    public_host = cfg.require(cfg.public_host, "network.public_host")
    poll_interval = int(cfg.require(cfg.endpoint_poll_sec, "network.endpoint_poll_sec"))
    app.state.cfg = cfg

    agent = await KuberboltAgent.from_config(cfg)
    try:
        registered = await agent.register_from_config()
        logger.info("=" * 60)
        logger.info(f"KUBERBOLT SELLER AGENT: {cfg.name}")
        logger.info(f"Pubkey: {agent.pubkey_hex}")
        logger.info(f"Listing event: {registered.get('listing_event_id')}")
        logger.info(f"Compute Server: http://{listen_host}:{listen_port}")
        logger.info(f"Advertised Financial Pod: {public_host}:{cfg.grpc_port}")
        logger.info("=" * 60)

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:
                pass  # Windows or non-main thread

        server = uvicorn.Server(uvicorn.Config(
            app=app,
            host=listen_host,
            port=listen_port,
            log_level="info",
            access_log=False,
        ))
        resolver_task = asyncio.create_task(agent.serve_endpoint_requests(
            host=public_host,
            port=cfg.grpc_port,
            poll_interval=poll_interval,
            db_path=cfg.ledger_path,
            stop_event=stop_event,
        ))
        server_task = asyncio.create_task(server.serve())

        done, pending = await asyncio.wait(
            [resolver_task, server_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        stop_event.set()
        server.should_exit = True
        for t in pending:
            t.cancel()
        for t in done:
            t.result()  # surface a crash in either task
    finally:
        await agent.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Seller agent stopped by user.")
