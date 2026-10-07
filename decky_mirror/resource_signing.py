import hmac
import secrets
from base64 import urlsafe_b64encode
from re import fullmatch

from .constants import RESOURCE_SIGNING_KEY
from .errors import InvalidResourceSignatureError

_SIGNING_KEY = secrets.token_bytes(32) if RESOURCE_SIGNING_KEY == "random" else RESOURCE_SIGNING_KEY.encode("utf-8")


def sign_resource_token(token: str) -> str:
    digest = hmac.digest(_SIGNING_KEY, token.encode("ascii"), "sha256")[:16]
    signature = urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{token}.{signature}"


def unsign_resource_token(signed_token: str) -> str:
    if not fullmatch(r"[A-Za-z0-9_=-]+\.[A-Za-z0-9_-]{22}", signed_token):
        raise InvalidResourceSignatureError("Invalid resource signature")
    token, signature = signed_token.split(".")
    expected_signature = sign_resource_token(token).split(".")[1]
    if not hmac.compare_digest(signature, expected_signature):
        raise InvalidResourceSignatureError("Invalid resource signature")
    return token
