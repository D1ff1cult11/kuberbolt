"""
Seller Agent Brain for Kuberbolt Network.

This service runs on Machine B (Seller) and provides:
1. Compute Server (FastAPI): Listens on localhost for compute requests forwarded
   by the local Go Financial Pod after L402 payment settlement. Uses Google Gemini
   to perform text summarization (or other AI tasks).
2. Endpoint Resolver (NIP-44 Listener): Subscribes to Nostr relays and listens for
   encrypted resolve_endpoint requests from Buyer agents, replying with this machine's
   local LAN IP and Financial Pod gRPC port.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

# Ensure repo root and brain are in sys.path
CURRENT_DIR = Path(__file__).resolve().parent
BRAIN_DIR = CURRENT_DIR.parent
REPO_ROOT = BRAIN_DIR.parent.parent
for p in [str(REPO_ROOT), str(BRAIN_DIR), str(CURRENT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from app.utils.network import get_local_ip
except ImportError:
    from utils.network import get_local_ip

try:
    from sdk.python.nostr_sdk_wrapper.agent import KuberboltAgent
except ImportError:
    try:
        from nostr_sdk_wrapper.agent import KuberboltAgent
    except ImportError:
        KuberboltAgent = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("kuberbolt.seller_agent")

# Configuration from Environment
BRAIN_HOST = os.getenv("BRAIN_HOST", "0.0.0.0")
BRAIN_PORT = int(os.getenv("BRAIN_PORT", "8001"))
FP_GRPC_PORT = int(os.getenv("FP_GRPC_PORT", "6001"))
SELLER_NOSTR_PRIVKEY = os.getenv("SELLER_NOSTR_PRIVKEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
DEFAULT_RELAY_LIST = ["wss://relay.damus.io", "wss://nos.lol"]
RELAYS_ENV = os.getenv("KUBERBOLT_RELAYS") or os.getenv("DEFAULT_RELAYS")
RELAY_URLS = [r.strip() for r in RELAYS_ENV.split(",")] if RELAYS_ENV else DEFAULT_RELAY_LIST
LEDGER_DB_PATH = os.getenv("LEDGER_DB_PATH", "seller_ledger.db")

# FastAPI App for Compute
app = FastAPI(title="Kuberbolt Seller Brain", version="1.0.0")


class ComputeRequest(BaseModel):
    service_kind: str
    job_spec_base64: str


class ComputeResponse(BaseModel):
    output_data_base64: str
    error: str = ""


async def summarize_text(text: str) -> str:
    """Summarize text using Google Gemini or fallback logic."""
    if not text.strip():
        return "No text provided to summarize."

    # If Google API Key is provided, call Gemini
    api_key = os.getenv("GOOGLE_API_KEY") or GOOGLE_API_KEY
    if api_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langchain_core.messages import HumanMessage

            llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                google_api_key=api_key,
                temperature=0.3,
            )
            prompt = (
                "You are an AI text summarizer running on the Kuberbolt autonomous agent network.\n"
                "Please provide a clear, high-quality, and concise summary of the following text:\n\n"
                f"{text}"
            )
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            return str(response.content)
        except Exception as e:
            logger.warning(f"LangChain Gemini call failed: {e}. Trying direct google.genai fallback...")
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-2.0-flash")
                resp = model.generate_content(f"Summarize the following text:\n\n{text}")
                return resp.text
            except Exception as e2:
                logger.error(f"Google Gemini generation failed: {e2}")
                # Fallback to local summarization if API call fails
                return f"[Gemini Error: {e2}] Extractive summary: " + " ".join(text.split()[:50]) + "..."
    else:
        logger.warning("GOOGLE_API_KEY not set. Using local offline summarizer fallback.")
        words = text.split()
        if len(words) <= 30:
            return f"[Offline Mode] {text}"
        return f"[Offline Mode Summary] {' '.join(words[:40])}..."


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "role": "seller_brain",
        "local_ip": get_local_ip(),
        "fp_grpc_port": FP_GRPC_PORT,
        "gemini_configured": bool(os.getenv("GOOGLE_API_KEY") or GOOGLE_API_KEY),
        "nostr_configured": bool(SELLER_NOSTR_PRIVKEY),
    }


@app.post("/compute", response_model=ComputeResponse)
async def handle_compute(req: ComputeRequest):
    """
    Compute endpoint called by the Go Financial Pod upon successful L402 payment settlement.
    Decodes job_spec_base64, executes the requested service, and returns output_data_base64.
    """
    logger.info(f"Received compute request for service_kind={req.service_kind}")

    try:
        raw_job_spec = base64.b64decode(req.job_spec_base64)
    except Exception as e:
        logger.error(f"Failed to decode base64 job spec: {e}")
        return ComputeResponse(output_data_base64="", error=f"Invalid base64 job spec: {e}")

    # Parse job spec payload
    text_to_process = ""
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

    logger.info(f"Processing compute job (input length: {len(text_to_process)} chars)...")

    # Perform computation based on service kind
    if req.service_kind in ("text-summarization", "summarization", "default"):
        summary_result = await summarize_text(text_to_process)
        output_payload = {
            "status": "completed",
            "service_kind": req.service_kind,
            "summary": summary_result,
        }
    else:
        # Generic echo or unknown service
        logger.warning(f"Unknown service kind {req.service_kind}, echoing response")
        output_payload = {
            "status": "completed",
            "service_kind": req.service_kind,
            "result": text_to_process,
        }

    output_bytes = json.dumps(output_payload, indent=2).encode("utf-8")
    output_b64 = base64.b64encode(output_bytes).decode("utf-8")

    logger.info(f"Compute job completed successfully for service_kind={req.service_kind}")
    return ComputeResponse(output_data_base64=output_b64, error="")


async def run_endpoint_resolver(stop_event: asyncio.Event):
    """
    Runs the Nostr NIP-44 encrypted DM listener for resolve_endpoint requests.
    """
    privkey = os.getenv("SELLER_NOSTR_PRIVKEY") or SELLER_NOSTR_PRIVKEY
    if not privkey:
        logger.warning(
            "SELLER_NOSTR_PRIVKEY is not set. Endpoint resolver daemon cannot start. "
            "Please register the seller agent on the SDK server and set SELLER_NOSTR_PRIVKEY."
        )
        return

    if KuberboltAgent is None:
        logger.error("KuberboltAgent SDK could not be imported.")
        return

    local_ip = get_local_ip()
    logger.info(
        f"Starting Seller NIP-44 Endpoint Resolver...\n"
        f"  - Local LAN IP: {local_ip}\n"
        f"  - FP gRPC Port: {FP_GRPC_PORT}\n"
        f"  - Relays: {RELAY_URLS}\n"
        f"  - DB Path: {LEDGER_DB_PATH}"
    )

    try:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            id_path = os.path.join(tmpdir, "seller_id.json")
            agent = await KuberboltAgent.from_existing_key(
                privkey_hex=privkey,
                identity_path=id_path,
                relay_urls=RELAY_URLS,
            )

        logger.info(f"Seller agent connected to Nostr relays. Pubkey: {agent.pubkey_hex}")
        logger.info("Listening for resolve_endpoint handshake requests from buyer agents...")

        await agent.serve_endpoint_requests(
            host=local_ip,
            port=FP_GRPC_PORT,
            poll_interval=3,
            db_path=LEDGER_DB_PATH,
            stop_event=stop_event,
        )
    except asyncio.CancelledError:
        logger.info("Endpoint resolver stopped.")
    except Exception as e:
        logger.error(f"Error in endpoint resolver: {e}", exc_info=True)


async def main():
    local_ip = get_local_ip()
    logger.info("=" * 60)
    logger.info("🚀 KUBERBOLT SELLER AGENT (Machine B)")
    logger.info("=" * 60)
    logger.info(f"Local LAN IP: {local_ip}")
    logger.info(f"Compute Server: http://{BRAIN_HOST}:{BRAIN_PORT}")
    logger.info(f"Financial Pod Target: {local_ip}:{FP_GRPC_PORT}")
    logger.info("=" * 60)

    stop_event = asyncio.Event()

    # Setup signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: stop_event.set())
        except NotImplementedError:
            pass  # Windows or non-main thread

    # Configure Uvicorn server
    config = uvicorn.Config(
        app=app,
        host=BRAIN_HOST,
        port=BRAIN_PORT,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)

    # Run both the compute server and the Nostr endpoint resolver
    resolver_task = asyncio.create_task(run_endpoint_resolver(stop_event))
    server_task = asyncio.create_task(server.serve())

    done, pending = await asyncio.wait(
        [resolver_task, server_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    stop_event.set()
    server.should_exit = True

    for t in pending:
        t.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Seller agent stopped by user.")
