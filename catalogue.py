import json
from base64 import b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from re import fullmatch
from typing import Any

from yarl import URL

from errors import InvalidCatalogueError, InvalidResourceError
from security import parse_http_url

SHA256_PATTERN = r"[0-9a-fA-F]{64}"
BASE64URL_PATTERN = r"[A-Za-z0-9_-]+"


def rewrite_catalogue(content: bytes, domain: str) -> list[dict[str, Any]]:
    try:
        catalogue = json.loads(content)
        if not isinstance(catalogue, list):
            raise TypeError("Expected a catalogue array")
        return [rewrite_plugin(plugin, domain) for plugin in catalogue]
    except (ValueError, KeyError, TypeError, InvalidResourceError) as error:
        raise InvalidCatalogueError("Invalid upstream catalogue") from error


def rewrite_plugin(plugin: dict[str, Any], domain: str) -> dict[str, Any]:
    if not isinstance(plugin, dict) or not isinstance(plugin.get("versions"), list):
        raise InvalidCatalogueError("Invalid upstream plugin")
    rewritten = dict(plugin)
    rewritten["versions"] = [
        rewrite_version(version, domain) for version in plugin["versions"]
    ]
    rewritten["image_url"] = encoded_resource_url(plugin["image_url"], domain)
    return rewritten


def rewrite_version(version: dict[str, Any], domain: str) -> dict[str, Any]:
    if not isinstance(version, dict):
        raise InvalidCatalogueError("Invalid upstream version")
    rewritten = dict(version)
    artifact = version.get("artifact")
    if artifact is None:
        validate_archive_hash(version["hash"])
        rewritten["artifact"] = f"https://{domain}/resources/hash/{version['hash']}"
    else:
        rewritten["artifact"] = encoded_resource_url(artifact, domain)
    return rewritten


def encoded_resource_url(url: str, domain: str) -> str:
    parse_http_url(url)
    return f"https://{domain}/resources/base64/{encode_url(url)}"


def encode_url(url: str) -> str:
    return urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")


def decode_resource_url(token: str) -> URL:
    if not fullmatch(BASE64URL_PATTERN, token):
        raise InvalidResourceError("Invalid resource URL encoding")
    try:
        url = b64decode(
            token + "=" * (-len(token) % 4), altchars=b"-_", validate=True
        ).decode("utf-8")
    except (ValueError, Base64Error) as error:
        raise InvalidResourceError("Invalid resource URL encoding") from error
    if encode_url(url) != token:
        raise InvalidResourceError("Non-canonical resource URL encoding")
    return parse_http_url(url)


def validate_archive_hash(archive_hash: str) -> None:
    if not isinstance(archive_hash, str) or not fullmatch(SHA256_PATTERN, archive_hash):
        raise InvalidResourceError("Expected a SHA-256 archive hash")


def archive_resource_url(archive_hash: str, cdn_domain: str) -> URL:
    validate_archive_hash(archive_hash)
    return parse_http_url(
        f"https://{cdn_domain}/file/steam-deck-homebrew/versions/{archive_hash}.zip"
    )
