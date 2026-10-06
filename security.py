import socket
from ipaddress import ip_address

from aiohttp.abc import ResolveResult
from aiohttp.resolver import ThreadedResolver
from yarl import URL

from errors import BlockedDestinationError, InvalidResourceError


class BlockedAddressLookupError(OSError):
    pass


def parse_http_url(value: str) -> URL:
    validate_url_text(value)
    try:
        url = URL(value, encoded=True)
        validate_http_url(url)
        return url
    except (ValueError, UnicodeError) as error:
        raise InvalidResourceError("Invalid resource URL") from error


def validate_url_text(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise InvalidResourceError("Expected a nonempty resource URL")
    if any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in value
    ):
        raise InvalidResourceError(
            "Resource URL contains whitespace or control characters"
        )


def validate_http_url(url: URL) -> None:
    if (
        url.scheme not in ("http", "https")
        or not url.host
        or url.user is not None
        or url.port is None
    ):
        raise InvalidResourceError(
            "Expected an absolute HTTP(S) URL without credentials"
        )


def is_public_address(value: str) -> bool:
    address = ip_address(value)
    return address.is_global and not address.is_multicast and not address.is_reserved


def validate_destination(url: URL) -> None:
    hostname = (url.host or "").rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise BlockedDestinationError("Resource destination must be public")
    validate_address_literal(hostname)


def validate_address_literal(hostname: str) -> None:
    try:
        address = ip_address(hostname)
    except ValueError:
        if ":" in hostname or hostname.replace(".", "").isdigit():
            raise InvalidResourceError("Invalid destination address")
        return
    if not is_public_address(str(address)):
        raise BlockedDestinationError("Resource destination must be public")


class PublicAddressResolver(ThreadedResolver):
    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_INET,
    ) -> list[ResolveResult]:
        addresses = await super().resolve(host, port, family)
        if not addresses:
            raise OSError("Destination has no resolved addresses")
        if any(not is_public_address(address["host"]) for address in addresses):
            raise BlockedAddressLookupError(
                "Resource destination must resolve to public addresses"
            )
        # Numeric results go directly to the connector, avoiding a second DNS lookup.
        return addresses
