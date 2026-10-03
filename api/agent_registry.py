"""
AgentRegistry — Redis-backed, multi-worker-safe session store.

Each record in Redis:
  HSET agent:{pubkey}
       token_hash    <32 bytes — SHA-256 of the bearer token>
       enc_privkey   <Fernet-encrypted hex private key>

Per-worker LRU cache avoids rebuilding KuberboltAgent on every request.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
from collections import OrderedDict
from typing import Any

<<<<<<< HEAD

class AgentRegistry:
    """Thread-safe registry of active KuberboltAgent instances in session."""
=======
import redis.asyncio as aioredis
from cryptography.fernet import Fernet
>>>>>>> feat/system-wiring

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REDIS_URL    = os.getenv("REDIS_URL", "redis://localhost:6379/0")
FERNET_KEY   = os.getenv("AGENT_FERNET_KEY", "")   # must be set in prod
KEY_PREFIX   = "agent:"
SESSION_TTL  = 7 * 24 * 3600  # 7 days

<<<<<<< HEAD
    async def register(self, agent: Any, session_token: str) -> str:
        async with self._lock:
            pubkey = agent.pubkey_hex
            self._agents[pubkey] = agent
            self._token_hashes[pubkey] = hashlib.sha256(
                session_token.encode()).digest()
            return pubkey
=======
# ---------------------------------------------------------------------------
# Redis client (lazy singleton, shared within a worker process)
# ---------------------------------------------------------------------------
_redis_client: aioredis.Redis | None = None
_redis_lock = asyncio.Lock()
>>>>>>> feat/system-wiring


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        async with _redis_lock:
            if _redis_client is None:
                _redis_client = aioredis.from_url(REDIS_URL, decode_responses=False)
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


# ---------------------------------------------------------------------------
# Per-worker LRU agent cache
# ---------------------------------------------------------------------------
class _LRUAgentCache:
    """
    Keeps a bounded set of warm KuberboltAgent objects in this worker's RAM.
    On a cache hit, we skip the Redis round-trip and agent reconstruction.
    On a cache miss, the registry fetches from Redis and populates the cache.
    """

    def __init__(self, maxsize: int = 256) -> None:
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._lock  = asyncio.Lock()
        self._max   = maxsize

    async def get(self, pubkey: str) -> Any | None:
        async with self._lock:
            if pubkey in self._cache:
                self._cache.move_to_end(pubkey)
                return self._cache[pubkey]
        return None

    async def put(self, pubkey: str, agent: Any) -> None:
        async with self._lock:
            if pubkey in self._cache:
                self._cache.move_to_end(pubkey)
            else:
                if len(self._cache) >= self._max:
                    _, evicted = self._cache.popitem(last=False)
                    if hasattr(evicted, "disconnect"):
                        await evicted.disconnect()
                self._cache[pubkey] = agent

    async def remove(self, pubkey: str) -> None:
        async with self._lock:
            agent = self._cache.pop(pubkey, None)
            if agent and hasattr(agent, "disconnect"):
                await agent.disconnect()

    async def clear(self) -> None:
        async with self._lock:
            agents = list(self._cache.values())
            self._cache.clear()
        for agent in agents:
            if hasattr(agent, "disconnect"):
                try:
                    await agent.disconnect()
                except Exception:
                    pass


_lru = _LRUAgentCache(maxsize=256)


# ---------------------------------------------------------------------------
# AgentRegistry
# ---------------------------------------------------------------------------
class AgentRegistry:
    """
    Multi-worker-safe registry backed by Redis.

    Authentication flow:
      register()     → store token_hash + encrypted privkey in Redis
      authenticate() → verify token against Redis, rebuild agent if needed,
                       cache agent in per-worker LRU
    """

    def __init__(self) -> None:
        if not FERNET_KEY:
            raise RuntimeError(
                "AGENT_FERNET_KEY is not set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            )
        self._fernet = Fernet(FERNET_KEY.encode())

    # ------------------------------------------------------------------
    # Public API (same surface as before)
    # ------------------------------------------------------------------

    async def register(self, agent: Any, session_token: str) -> str:
        """Store a new session in Redis and warm the local LRU."""
        pubkey      = agent.pubkey_hex
        privkey_hex = agent.keys.secret_key().to_hex()

        token_hash  = hashlib.sha256(session_token.encode()).digest()
        enc_privkey = self._fernet.encrypt(privkey_hex.encode())

        r = await get_redis()
        await r.hset(
            KEY_PREFIX + pubkey,
            mapping={"token_hash": token_hash, "enc_privkey": enc_privkey},
        )
        await r.expire(KEY_PREFIX + pubkey, SESSION_TTL)

        # Warm this worker's cache immediately
        await _lru.put(pubkey, agent)
        return pubkey

    async def authenticate(self, pubkey: str, session_token: str) -> Any | None:
        """
        Verify the bearer token against Redis.
        Returns a live KuberboltAgent (from LRU cache or freshly rebuilt).
        """
        # 1. Fast path — agent already warm in this worker
        cached = await _lru.get(pubkey)
        if cached is not None:
            # Still need to verify the token on every call (no blind trust of LRU)
            r = await get_redis()
            row = await r.hgetall(KEY_PREFIX + pubkey)
            if not row:
                await _lru.remove(pubkey)
                return None
            stored_hash  = row[b"token_hash"]
            supplied     = hashlib.sha256(session_token.encode()).digest()
            if not hmac.compare_digest(stored_hash, supplied):
                return None
            return cached

        # 2. Slow path — fetch from Redis and rebuild agent
        r   = await get_redis()
        row = await r.hgetall(KEY_PREFIX + pubkey)
        if not row:
            return None

        stored_hash = row[b"token_hash"]
        supplied    = hashlib.sha256(session_token.encode()).digest()
        if not hmac.compare_digest(stored_hash, supplied):
            return None

        privkey_hex = self._fernet.decrypt(row[b"enc_privkey"]).decode()
        agent = await _rebuild_agent(pubkey, privkey_hex)
        await _lru.put(pubkey, agent)
        return agent

    async def get(self, pubkey: str) -> Any | None:
        """Return agent if session exists (no token check). Used internally."""
        cached = await _lru.get(pubkey)
        if cached is not None:
            return cached
        r = await get_redis()
        if not await r.exists(KEY_PREFIX + pubkey):
            return None
        # Can't rebuild without token verification — return None for unauthenticated get
        return None

    async def remove(self, pubkey: str) -> None:
        """Revoke session immediately (removes from Redis + LRU)."""
        r = await get_redis()
        await r.delete(KEY_PREFIX + pubkey)
        await _lru.remove(pubkey)


# ---------------------------------------------------------------------------
# Agent reconstruction helper
# ---------------------------------------------------------------------------
async def _rebuild_agent(pubkey: str, privkey_hex: str) -> Any:
    """
    Reconstruct a KuberboltAgent from its private key hex.
    Import is deferred to avoid circular imports.
    """
    import os, tempfile
    try:
        from sdk.python.nostr_sdk_wrapper.agent import KuberboltAgent
    except ImportError:
        from nostr_sdk_wrapper.agent import KuberboltAgent

    from api.dependencies import DEFAULT_RELAYS

    with tempfile.TemporaryDirectory() as tmpdir:
        identity_path = os.path.join(tmpdir, "id.json")
        agent = await KuberboltAgent.from_existing_key(
            privkey_hex,
            identity_path=identity_path,
            relay_urls=DEFAULT_RELAYS,
        )
    return agent


# ---------------------------------------------------------------------------
# Singleton + FastAPI dependency
# ---------------------------------------------------------------------------
_registry: AgentRegistry | None = None
_registry_lock = asyncio.Lock()


async def get_agent_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        async with _registry_lock:
            if _registry is None:
                _registry = AgentRegistry()
    return _registry
