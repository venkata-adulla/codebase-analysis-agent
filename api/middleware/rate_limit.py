import time
from typing import Callable
from fastapi import Request, HTTPException, status
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from core.database import get_redis_client
from core.config import get_settings

settings = get_settings()

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=f"redis://{settings.redis_host}:{settings.redis_port}",
    default_limits=[f"{settings.rate_limit_per_minute}/minute"]
)


def get_rate_limiter():
    """Get rate limiter instance."""
    return limiter
