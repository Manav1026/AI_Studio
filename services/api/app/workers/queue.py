import redis

from app.core.config import get_settings

_conn = None


def get_queue_connection() -> redis.Redis:
    """RQ needs a bytes (non-decoding) Redis connection."""
    global _conn
    if _conn is None:
        _conn = redis.Redis.from_url(get_settings().redis_url)
    return _conn
