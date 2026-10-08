from fastapi import Request
from slowapi import Limiter

RATE_LIMIT = "5/second"


def request_key(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    if "hash" in request.path_params:
        return str((ip, request.path_params["hash"]))
    if "base64url" in request.path_params:
        return str((ip, request.path_params["base64url"]))
    return ip


limiter = Limiter(
    key_func=request_key,
    key_style="endpoint",
    storage_uri="memory://",
    strategy="fixed-window",
    headers_enabled=False,
)
