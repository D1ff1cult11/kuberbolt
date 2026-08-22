from datetime import datetime, timezone
import os
import sys
import tempfile
from pathlib import Path
from fastapi import APIRouter, HTTPException

from api.dependencies import DEFAULT_RELAYS
from api.schemas.agents import RegisterAgentRequest, RegisterAgentResponse

sdk_path = Path(__file__).resolve().parent.parent.parent / "sdk" / "python"
if str(sdk_path) not in sys.path:
    sys.path.insert(0, str(sdk_path))

try:
    from nostr_sdk_wrapper.agent import KuberboltAgent
except ImportError:
    from kuberbolt_nostr.agent import KuberboltAgent

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.post("/register", response_model=RegisterAgentResponse)
async def register_agent(req: RegisterAgentRequest):
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            identity_path = os.path.join(tmpdir, "id.json")
            agent = await KuberboltAgent.create(
                identity_path=identity_path,
                relay_urls=req.relays or DEFAULT_RELAYS,
            )
            try:
                result = await agent.register(
                    role=req.role,
                    display_name=req.display_name,
                    about=req.about,
                    lightning_address=req.lightning.lightning_address or req.lightning.lnurl,
                    service=req.service.model_dump() if req.service else None,
                )
                if req.picture_url:
                    profile_event = await agent.publish_profile(
                        name=req.display_name,
                        about=req.about,
                        picture=req.picture_url,
                        lud16=req.lightning.lightning_address or req.lightning.lnurl,
                    )
                    result["profile_event_id"] = profile_event.id().to_hex()
            finally:
                await agent.disconnect()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))

    return RegisterAgentResponse(
        agent_pubkey=result["nostr_pubkey"],
        agent_privkey=result["nostr_privkey"],
        role=req.role,
        lightning=req.lightning,
        service=req.service,
        profile_event_id=result["profile_event_id"],
        listing_event_id=result["listing_event_id"],
        status="registered",
        registered_at=datetime.now(timezone.utc),
    )
