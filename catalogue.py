import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from re import fullmatch
from typing import Any

from yarl import URL

from errors import InvalidCatalogueError, InvalidResourceError
from security import parse_url

SHA256_PATTERN = r"[0-9a-fA-F]{64}"
BASE64URL_PATTERN = r"(?:[A-Za-z0-9_-]{4})*(?:[A-Za-z0-9_-]{2}==|[A-Za-z0-9_-]{3}=)?"


def substitute_catalogue_resource_urls(
    content: bytes, domain: str
) -> list[dict[str, Any]]:
    try:
        catalogue = json.loads(content)
        if not isinstance(catalogue, list):
            raise TypeError("Expected a catalogue array")
        return [substitute_plugin_resource_urls(plugin, domain) for plugin in catalogue]
    except (ValueError, KeyError, TypeError, InvalidResourceError) as error:
        raise InvalidCatalogueError("Invalid upstream catalogue") from error


def substitute_plugin_resource_urls(
    plugin: dict[str, Any], domain: str
) -> dict[str, Any]:
    if not isinstance(plugin, dict) or not isinstance(plugin.get("versions"), list):
        raise InvalidCatalogueError("Invalid upstream plugin")
    substituted_plugin = dict(plugin)
    substituted_plugin["versions"] = [
        substitute_version_artifact_url(version, domain)
        for version in plugin["versions"]
    ]
    substituted_plugin["image_url"] = build_resource_url(plugin["image_url"], domain)
    return substituted_plugin


def substitute_version_artifact_url(
    version: dict[str, Any], domain: str
) -> dict[str, Any]:
    if not isinstance(version, dict):
        raise InvalidCatalogueError("Invalid upstream version")
    substituted_version = dict(version)
    substituted_version["artifact"] = build_mirror_artifact_url(version, domain)
    return substituted_version


def build_mirror_artifact_url(version: dict[str, Any], domain: str) -> str:
    artifact = version.get("artifact")
    if artifact is not None:
        return build_resource_url(artifact, domain)
    validate_archive_hash(version["hash"])
    return f"https://{domain}/resources/hash/{version['hash']}"


def build_resource_url(url: str, domain: str) -> str:
    parse_url(url)  # Called to validate the resource URL.
    return f"https://{domain}/resources/base64/{encode_resource_url(url)}"


def encode_resource_url(url: str) -> str:
    return urlsafe_b64encode(url.encode("utf-8")).decode("ascii")


def decode_resource_url(token: str) -> URL:
    if not fullmatch(BASE64URL_PATTERN, token):
        raise InvalidResourceError("Invalid resource URL encoding")
    try:
        url = urlsafe_b64decode(token).decode("utf-8")
    except (ValueError, Base64Error) as error:
        raise InvalidResourceError("Invalid resource URL encoding") from error
    return parse_url(url)


def validate_archive_hash(archive_hash: str) -> None:
    if not isinstance(archive_hash, str) or not fullmatch(SHA256_PATTERN, archive_hash):
        raise InvalidResourceError("Expected a SHA-256 archive hash")


def build_archive_url(archive_hash: str, cdn_domain: str) -> URL:
    validate_archive_hash(archive_hash)
    return parse_url(
        f"https://{cdn_domain}/file/steam-deck-homebrew/versions/{archive_hash}.zip"
    )
