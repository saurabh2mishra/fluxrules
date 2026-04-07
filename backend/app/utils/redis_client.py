import redis
from app.config import settings

_redis_client = None
_redis_available = None


def get_redis_client():
    global _redis_client, _redis_available
    
    # If we already know Redis is not available, return None quickly
    if _redis_available is False:
        return None
    
    if _redis_client is None:
        try:
            _redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True,
                socket_timeout=0.5,  # 500ms timeout
                socket_connect_timeout=0.5,  # 500ms connect timeout
                retry_on_timeout=False
            )
            # Quick ping test
            _redis_client.ping()
            _redis_available = True
        except Exception:
            _redis_available = False
            _redis_client = None
    
    return _redis_client


def is_redis_available() -> bool:
    """Check if Redis is available without blocking."""
    global _redis_available
    if _redis_available is None:
        get_redis_client()
    return _redis_available is True