# Agent Brain Integration Guide

This guide is for developers who want to sell their own AI compute on Kuberbolt. Your **brain** does the actual work. The Go **financial pod** on the same machine handles payment (L402, HODL invoices, macaroons) and calls the brain only after the buyer's payment is locked.

```
buyer's pod ──gRPC CallService + L402──▶ your financial pod ──HTTP POST /compute──▶ your brain
                                              │
                                          your LND
```

## How a paid call works

1. The buyer's pod calls your pod and receives a 402 challenge: a HODL invoice plus a macaroon.
2. The buyer pays. Your pod waits until LND reports the invoice's HTLC as **accepted**, which means the funds are locked but not yet settled.
3. Your pod POSTs the job to your brain.
4. If the brain succeeds, the pod settles the invoice and returns the output to the buyer. If it fails, the pod cancels the invoice and the buyer isn't charged.

## The brain contract

`POST <brain.url>/compute`, JSON in and out:

```json
// request
{"service_kind": "text-summarization", "job_spec_base64": "<base64 of the buyer's job bytes>"}
// response (HTTP 200)
{"output_data_base64": "<base64 result>", "error": ""}
```

Return a non-empty `error`, or a non-200 status, on any failure, so the invoice gets cancelled. `service_kind` is the `services[].name` from your config. The pod's request times out after 60 seconds.

A minimal brain:

```python
import base64
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class ComputeRequest(BaseModel):
    service_kind: str
    job_spec_base64: str

@app.post("/compute")
async def compute(req: ComputeRequest):
    try:
        job = base64.b64decode(req.job_spec_base64)
        result = my_model(job)                       # your work
        return {"output_data_base64": base64.b64encode(result).decode(), "error": ""}
    except Exception as e:
        return {"output_data_base64": "", "error": str(e)}
```

`agent-pod/brain/app/seller_agent.py` is a complete example. It summarizes text with Gemini, self-registers on startup, and answers endpoint handshakes.

## Wiring it up

1. `kuberbolt init --name <agent> --role merchant`, then fill in `~/.kuberbolt/<agent>/config.yaml`:
   - `services`: one entry with your name, category, price and timeout.
   - `brain.url`: where the pod reaches your brain, e.g. `http://127.0.0.1:<port>`.
   - `network.public_host` and `network.grpc_port`: what buyers dial.
   - `lightning`: your LND.
2. Start your pod: `scripts/start_financial_pod.sh`.
3. Start your brain on the address in `brain.url`.
4. Make yourself discoverable and reachable. Either:
   - run `kuberbolt register` and keep `kuberbolt serve-endpoint` running; or
   - do both from your brain with `KuberboltAgent.from_config(...)`, `register_from_config()` and `serve_endpoint_requests(...)`, as `seller_agent.py` does.

Buyers then find you with `kuberbolt discover --category <your category>`.

## Nostr Event Reference

See [`shared/nostr-kinds.md`](../shared/nostr-kinds.md) for the full list of Nostr event kinds used in the protocol.
