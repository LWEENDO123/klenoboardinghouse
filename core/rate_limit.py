from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request
from functools import wraps

# ✅ Create a limiter instance
limiter = Limiter(
    key_func=get_remote_address,
    headers_enabled=True,
    auto_check=True
)

# ✅ A decorator wrapper that doesn’t leak args/kwargs into FastAPI
def limit(limit_value: str):
    """
    Wrapper around limiter.limit that guarantees request is always passed
    without exposing *args/**kwargs to FastAPI as query params.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Ensure request is in kwargs if not already
            if "request" not in kwargs:
                for arg in args:
                    if isinstance(arg, Request):
                        kwargs["request"] = arg
                        break
            return await func(*args, **kwargs)
        return limiter.limit(limit_value)(wrapper)
    return decorator
