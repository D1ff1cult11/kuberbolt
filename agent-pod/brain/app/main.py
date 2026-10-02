from __future__ import annotations

import base64

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.langchain_agent import run_job


app = FastAPI(title="Kuberbolt Brain Pod")


class ComputeRequest(BaseModel):
    service_kind: str
    job_spec_base64: str


class ComputeResponse(BaseModel):
    output_data_base64: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/compute", response_model=ComputeResponse)
async def compute(request: ComputeRequest) -> ComputeResponse:
    try:
        job_spec = base64.b64decode(request.job_spec_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="job_spec_base64 must be valid base64") from exc

    output = await run_job(request.service_kind, job_spec)
    return ComputeResponse(output_data_base64=base64.b64encode(output).decode())
