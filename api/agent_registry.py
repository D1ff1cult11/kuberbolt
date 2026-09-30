import asyncio
import hashlib
import hmac
from typing import Any


class AgentRegistry:
    """Thread-safe registry of active KuberboltAgent instances in session."""

    def __init__(self):
        self._agents: dict[str, Any] = {}
        self._token_hashes: dict[str, bytes] = {}
        self._lock = asyncio.Lock()

    async def register(self, agent: Any, session_token: str) -> str:
        async with self._lock:
            pubkey = agent.pubkey_hex
            self._agents[pubkey] = agent
            self._token_hashes[pubkey] = hashlib.sha256(
                session_token.encode()).digest()
            return pubkey

    async def authenticate(self, pubkey: str, session_token: str) -> Any | None:
        async with self._lock:
            token_hash = self._token_hashes.get(pubkey)
            if token_hash is None:
                return None
            supplied_hash = hashlib.sha256(session_token.encode()).digest()
            if not hmac.compare_digest(token_hash, supplied_hash):
                return None
            return self._agents.get(pubkey)

    async def get(self, pubkey: str) -> Any | None:
        async with self._lock:
            return self._agents.get(pubkey)

    async def remove(self, pubkey: str) -> None:
        async with self._lock:
            agent = self._agents.pop(pubkey, None)
            self._token_hashes.pop(pubkey, None)
            if agent and hasattr(agent, "disconnect"):
                await agent.disconnect()


_registry = AgentRegistry()


async def get_agent_registry() -> AgentRegistry:
    return _registry
