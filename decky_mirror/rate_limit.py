from fastapi import Request
from slowapi import Limiter

RATE_LIMIT = "5/second"


def request_key(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{ip}:{request.url.path}"


limiter = Limiter(
    key_func=request_key,
    storage_uri="memory://",
    strategy="fixed-window",
    headers_enabled=False,
)
