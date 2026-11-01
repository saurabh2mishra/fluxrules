import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from fluxrules.api.config import settings

_redis_client = None
_redis_available = None


def get_redis_client():
    global _redis_client, _redis_available

    if _redis_available is False:
        return None

    if _redis_client is None:
        try:
            options = {
                "host": settings.REDIS_HOST,
                "port": settings.REDIS_PORT,
                "db": settings.REDIS_DB,
                "decode_responses": True,
                "socket_timeout": 0.5,
                "socket_connect_timeout": 0.5,
            }
            # Probe once without retries: with redis-py's default retries a
            # missing server cost several seconds here. The client kept for
            # use keeps the default retries (the event queue relies on them).
            probe = redis.Redis(**options, retry=Retry(NoBackoff(), 0))
            try:
                probe.ping()
            finally:
                probe.close()
            _redis_client = redis.Redis(**options)
            _redis_available = True
        except Exception:
            _redis_available = False
            _redis_client = None

    return _redis_client


def is_redis_available() -> bool:
    global _redis_available
    if _redis_available is None:
        get_redis_client()
    return _redis_available is True
