"""Caching service with Redis backend and transparent high-performance in-memory fallback."""

from __future__ import annotations

import time
from typing import Any, Optional

import orjson

from app.monitoring.logger import get_logger

logger = get_logger("services.cache")

# Try importing redis async client
try:
    import redis.asyncio as aioredis
    _REDIS_INSTALLED = True
except ImportError:
    aioredis = None  # type: ignore
    _REDIS_INSTALLED = False


class CacheService:
    """Thread-safe, async caching layer with Redis support and in-memory TTL fallback."""

    def __init__(self) -> None:
        self._redis: Optional[Any] = None
        self._fallback_store: dict[str, tuple[Any, float]] = {}  # key -> (value, expire_at)
        self._is_redis_connected: bool = False

    async def connect(self, redis_url: str = "redis://localhost:6379/0", max_connections: int = 20) -> bool:
        """Attempt connection to Redis; fall back gracefully to in-memory on failure."""
        if not _REDIS_INSTALLED:
            logger.info("redis-py not installed; operating in in-memory cache mode")
            self._is_redis_connected = False
            return False

        try:
            self._redis = aioredis.from_url(
                redis_url,
                max_connections=max_connections,
                decode_responses=True,
                socket_timeout=3.0,
            )
            # Ping test
            await self._redis.ping()
            self._is_redis_connected = True
            logger.info("Connected to Redis cache", url=redis_url.split("@")[-1])
            return True
        except Exception as exc:
            self._is_redis_connected = False
            self._redis = None
            logger.warning("Redis unavailable; falling back to in-memory caching", error=str(exc))
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis is not None:
            try:
                await self._redis.close()
            except Exception:
                pass
            self._redis = None
            self._is_redis_connected = False

    async def get(self, key: str) -> Optional[str]:
        """Fetch raw string value."""
        if self._is_redis_connected and self._redis:
            try:
                return await self._redis.get(key)
            except Exception as exc:
                logger.warning("Redis GET failed, checking fallback", error=str(exc))

        # In-memory fallback
        now = time.monotonic()
        item = self._fallback_store.get(key)
        if item is not None:
            val, expire_at = item
            if expire_at == 0.0 or expire_at > now:
                return str(val) if not isinstance(val, str) else val
            else:
                del self._fallback_store[key]
        return None

    async def set(self, key: str, value: str, expire_seconds: int = 300) -> None:
        """Set raw string value with TTL."""
        if self._is_redis_connected and self._redis:
            try:
                await self._redis.set(key, value, ex=expire_seconds)
                return
            except Exception as exc:
                logger.warning("Redis SET failed, using in-memory", error=str(exc))

        # In-memory fallback
        expire_at = (time.monotonic() + expire_seconds) if expire_seconds > 0 else 0.0
        self._fallback_store[key] = (value, expire_at)
        self._prune_fallback_if_needed()

    async def get_json(self, key: str) -> Optional[Any]:
        """Retrieve and deserialize JSON value."""
        raw = await self.get(key)
        if raw is None:
            return None
        try:
            return orjson.loads(raw)
        except Exception as exc:
            logger.error("JSON deserialization failed", key=key, error=str(exc))
            return None

    async def set_json(self, key: str, value: Any, expire_seconds: int = 300) -> None:
        """Serialize and set JSON value with TTL."""
        try:
            raw = orjson.dumps(value).decode("utf-8")
            await self.set(key, raw, expire_seconds=expire_seconds)
        except Exception as exc:
            logger.error("JSON serialization failed", key=key, error=str(exc))

    async def delete(self, key: str) -> None:
        """Delete key from cache."""
        if self._is_redis_connected and self._redis:
            try:
                await self._redis.delete(key)
            except Exception:
                pass
        self._fallback_store.pop(key, None)

    async def publish(self, channel: str, message: str) -> None:
        """Publish message to Redis pub/sub if available."""
        if self._is_redis_connected and self._redis:
            try:
                await self._redis.publish(channel, message)
            except Exception as exc:
                logger.warning("Redis publish failed", channel=channel, error=str(exc))

    def _prune_fallback_if_needed(self) -> None:
        """Periodically prune expired keys from in-memory fallback store."""
        if len(self._fallback_store) > 1000:
            now = time.monotonic()
            expired = [k for k, (_, exp) in self._fallback_store.items() if exp > 0 and exp <= now]
            for k in expired:
                del self._fallback_store[k]

    @property
    def is_redis_available(self) -> bool:
        """Return whether active backend is Redis."""
        return self._is_redis_connected
