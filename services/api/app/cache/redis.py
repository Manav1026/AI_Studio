"""Redis: ephemeral cache, OAuth state, rate-limit state, idempotency keys and job queue.
Never the authoritative record — PostgreSQL is."""
import json
from typing import Any

import redis

from app.core.config import get_settings
from app.core.errors import RateLimited

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


def reset_redis_client() -> None:
    global _client
    _client = None


def cache_get_json(key: str) -> Any | None:
    raw = get_redis().get(key)
    return json.loads(raw) if raw else None


def cache_set_json(key: str, value: Any, ttl_seconds: int) -> None:
    get_redis().set(key, json.dumps(value, default=str), ex=ttl_seconds)


def cache_delete_prefix(prefix: str) -> int:
    r = get_redis()
    n = 0
    for key in r.scan_iter(match=f"{prefix}*", count=500):
        n += r.delete(key)
    return n


def pop_json(key: str) -> Any | None:
    """Atomic get-and-delete (used for one-time OAuth state)."""
    raw = get_redis().getdel(key)
    return json.loads(raw) if raw else None


def enforce_rate_limit(bucket: str, subject: str, limit_per_minute: int) -> None:
    """Fixed-window limiter; good enough for a prototype and keeps the same call sites for a
    sliding-window/token-bucket implementation later."""
    import time

    window = int(time.time() // 60)
    key = f"rl:{bucket}:{subject}:{window}"
    r = get_redis()
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, 70)
    count, _ = pipe.execute()
    if int(count) > limit_per_minute:
        raise RateLimited(f"Rate limit exceeded for {bucket}; try again in a minute",
                          details={"limit_per_minute": limit_per_minute})


def ping() -> bool:
    try:
        return bool(get_redis().ping())
    except redis.RedisError:
        return False
