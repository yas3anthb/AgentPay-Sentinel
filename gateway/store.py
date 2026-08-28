"""Redis-backed shared state: idempotency records, distributed locks,
delegation-revocation set, velocity counters.

`REDIS_URL=memory://` swaps in an in-process implementation with the same
surface so unit tests and offline demos don't need a server. It is explicitly
NOT safe across processes and refuses to be used outside dev.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import redis.asyncio as aioredis

from gateway.config import get_settings

REVOCATION_SET = "agentpay:revoked_delegations"


class MemoryStore:
    """Single-process stand-in for Redis. Dev/test only."""

    def __init__(self) -> None:
        self._kv: dict[str, tuple[Any, float | None]] = {}
        self._sets: dict[str, set[str]] = {}
        self._zsets: dict[str, dict[str, float]] = {}
        self._lock = asyncio.Lock()

    def _alive(self, key: str) -> bool:
        item = self._kv.get(key)
        if item is None:
            return False
        _, exp = item
        if exp is not None and exp < time.time():
            self._kv.pop(key, None)
            return False
        return True

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> str | None:
        return self._kv[key][0] if self._alive(key) else None

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self._kv[key] = (value, time.time() + ex if ex else None)
        return True

    async def set_nx(self, key: str, value: str, ex: int | None = None) -> bool:
        async with self._lock:
            if self._alive(key):
                return False
            self._kv[key] = (value, time.time() + ex if ex else None)
            return True

    async def delete_if_value(self, key: str, value: str) -> bool:
        async with self._lock:
            if self._alive(key) and self._kv[key][0] == value:
                self._kv.pop(key, None)
                return True
            return False

    async def sadd(self, key: str, member: str) -> None:
        self._sets.setdefault(key, set()).add(member)

    async def srem(self, key: str, member: str) -> None:
        self._sets.setdefault(key, set()).discard(member)

    async def sismember(self, key: str, member: str) -> bool:
        return member in self._sets.get(key, set())

    async def smembers(self, key: str) -> set[str]:
        return set(self._sets.get(key, set()))

    async def zadd_window(self, key: str, window_seconds: int) -> int:
        now = time.time()
        z = self._zsets.setdefault(key, {})
        for m, ts in list(z.items()):
            if ts < now - window_seconds:
                z.pop(m, None)
        z[uuid.uuid4().hex] = now
        return len(z)

    async def zcount_window(self, key: str, window_seconds: int) -> int:
        now = time.time()
        z = self._zsets.get(key, {})
        return sum(1 for ts in z.values() if ts >= now - window_seconds)

    async def publish(self, channel: str, message: str) -> int:
        """No-op: the in-process store has no subscribers to fan out to."""
        return 0

    async def close(self) -> None:
        return None


class RedisStore:
    _UNLOCK = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("DEL", KEYS[1])
    else
        return 0
    end
    """

    def __init__(self, url: str) -> None:
        self._r = aioredis.from_url(url, decode_responses=True)

    async def ping(self) -> bool:
        return bool(await self._r.ping())

    async def get(self, key: str) -> str | None:
        return await self._r.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        return bool(await self._r.set(key, value, ex=ex))

    async def set_nx(self, key: str, value: str, ex: int | None = None) -> bool:
        return bool(await self._r.set(key, value, nx=True, ex=ex))

    async def delete_if_value(self, key: str, value: str) -> bool:
        return bool(await self._r.eval(self._UNLOCK, 1, key, value))

    async def sadd(self, key: str, member: str) -> None:
        await self._r.sadd(key, member)

    async def srem(self, key: str, member: str) -> None:
        await self._r.srem(key, member)

    async def sismember(self, key: str, member: str) -> bool:
        return bool(await self._r.sismember(key, member))

    async def smembers(self, key: str) -> set[str]:
        return set(await self._r.smembers(key))

    async def zadd_window(self, key: str, window_seconds: int) -> int:
        now = time.time()
        pipe = self._r.pipeline()
        pipe.zremrangebyscore(key, "-inf", now - window_seconds)
        pipe.zadd(key, {uuid.uuid4().hex: now})
        pipe.zcard(key)
        pipe.expire(key, window_seconds * 2)
        result = await pipe.execute()
        return int(result[2])

    async def zcount_window(self, key: str, window_seconds: int) -> int:
        now = time.time()
        return int(await self._r.zcount(key, now - window_seconds, "+inf"))

    async def publish(self, channel: str, message: str) -> int:
        return int(await self._r.publish(channel, message))

    async def close(self) -> None:
        await self._r.aclose()


_store: RedisStore | MemoryStore | None = None


def get_store() -> RedisStore | MemoryStore:
    global _store
    if _store is None:
        settings = get_settings()
        if settings.redis_url.startswith("memory://"):
            if settings.environment == "production":
                raise RuntimeError("memory:// store is not permitted in production")
            _store = MemoryStore()
        else:
            _store = RedisStore(settings.redis_url)
    return _store


async def reset_store() -> None:
    global _store
    if _store is not None:
        await _store.close()
    _store = None


class DistributedLock:
    """`async with DistributedLock(key)` — fails closed: if the lock cannot be
    taken we do not proceed with the check-then-issue step."""

    def __init__(self, key: str, ttl: int | None = None) -> None:
        self.key = f"agentpay:lock:{key}"
        self.token = uuid.uuid4().hex
        self.ttl = ttl or get_settings().lock_ttl_seconds
        self.acquired = False

    async def __aenter__(self) -> "DistributedLock":
        store = get_store()
        for _ in range(50):
            if await store.set_nx(self.key, self.token, ex=self.ttl):
                self.acquired = True
                return self
            await asyncio.sleep(0.05)
        raise TimeoutError(f"could not acquire lock {self.key}")

    async def __aexit__(self, *exc: object) -> None:
        if self.acquired:
            await get_store().delete_if_value(self.key, self.token)
