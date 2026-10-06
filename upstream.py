from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from urllib.parse import quote

import aiohttp
from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask
from starlette.types import Receive, Scope, Send
from yarl import URL

import constants
from errors import (
    BlockedDestinationError,
    RedirectLimitError,
    UpstreamRequestError,
    UpstreamTimeoutError,
)
from security import (
    BlockedAddressLookupError,
    PublicAddressResolver,
    parse_http_url,
    validate_destination,
)

MAX_RESOURCE_REDIRECTS = 10
UPSTREAM_TIMEOUT_SECONDS = 30
STREAM_CHUNK_BYTES = 64 * 1024
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
STORE_RESPONSE_HEADERS = (
    "content-type",
    "content-disposition",
    "etag",
    "last-modified",
    "retry-after",
    "location",
)
RESOURCE_RESPONSE_HEADERS = STORE_RESPONSE_HEADERS + (
    "content-length",
    "content-encoding",
    "content-range",
    "accept-ranges",
)


@dataclass(frozen=True)
class StoreResponse:
    status: int
    content: bytes
    headers: dict[str, str]

    def to_response(self) -> Response:
        return Response(self.content, status_code=self.status, headers=self.headers)


class UpstreamClient:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch_catalogue(
        self, parameters: dict[str, str | list[str]], decky_version: str | None
    ) -> StoreResponse:
        url = parse_http_url(
            f"https://{constants.TARGET_STORE_DOMAIN}/plugins"
        ).with_query(parameters)
        headers = (
            {"X-Decky-Version": decky_version} if decky_version is not None else {}
        )
        return await self.fetch_store_response("GET", url, headers)

    async def record_install(
        self, plugin_name: str, version_name: str, is_update: bool
    ) -> StoreResponse:
        url = build_increment_url(plugin_name, version_name, is_update)
        return await self.fetch_store_response("POST", url)

    async def fetch_store_response(
        self,
        method: str,
        url: URL,
        headers: dict[str, str] | None = None,
    ) -> StoreResponse:
        validate_destination(url)
        with translate_upstream_errors():
            async with self.session.request(
                method,
                url,
                headers=headers,
                allow_redirects=False,
                auto_decompress=True,
            ) as response:
                content = await response.read()
                return StoreResponse(
                    response.status,
                    content,
                    select_headers(response, STORE_RESPONSE_HEADERS),
                )

    async def open_resource(self, url: URL) -> aiohttp.ClientResponse:
        for redirect_count in range(MAX_RESOURCE_REDIRECTS + 1):
            response = await self.request_resource(url)
            if response.status not in REDIRECT_STATUSES:
                return response
            url = resolve_redirect(response, redirect_count)
        raise RedirectLimitError("Upstream exceeded the resource redirect limit")

    async def request_resource(self, url: URL) -> aiohttp.ClientResponse:
        validate_destination(url)
        with translate_upstream_errors():
            return await self.session.request(
                "GET", url, allow_redirects=False, auto_decompress=False
            )


def build_increment_url(plugin_name: str, version_name: str, is_update: bool) -> URL:
    url = parse_http_url(
        f"https://{constants.TARGET_STORE_DOMAIN}/plugins/{quote(plugin_name, safe='')}"
        f"/versions/{quote(version_name, safe='')}/increment"
    )
    return url.with_query({"isUpdate": str(is_update).lower()})


def resolve_redirect(response: aiohttp.ClientResponse, redirect_count: int) -> URL:
    try:
        if redirect_count == MAX_RESOURCE_REDIRECTS:
            raise RedirectLimitError("Upstream exceeded the resource redirect limit")
        location = response.headers.get("Location")
        if not location:
            raise UpstreamRequestError("Upstream redirect has no destination")
        return parse_http_url(str(response.url.join(URL(location, encoded=True))))
    finally:
        response.close()


@contextmanager
def translate_upstream_errors() -> Iterator[None]:
    try:
        yield
    except TimeoutError as error:
        raise UpstreamTimeoutError("Upstream timed out") from error
    except aiohttp.ClientConnectorError as error:
        if isinstance(error.os_error, BlockedAddressLookupError):
            raise BlockedDestinationError(
                "Resource destination must be public"
            ) from error
        raise UpstreamRequestError("Unable to connect to upstream") from error
    except (aiohttp.ClientError, OSError) as error:
        raise UpstreamRequestError("Upstream request failed") from error


def select_headers(
    response: aiohttp.ClientResponse, names: tuple[str, ...]
) -> dict[str, str]:
    return {name: response.headers[name] for name in names if name in response.headers}


class ResourceStreamingResponse(StreamingResponse):
    def __init__(self, upstream_response: aiohttp.ClientResponse):
        self.upstream_response = upstream_response
        super().__init__(
            stream_resource(upstream_response),
            status_code=upstream_response.status,
            headers=select_headers(upstream_response, RESOURCE_RESPONSE_HEADERS),
            background=BackgroundTask(close_resource, upstream_response),
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.upstream_response.close()


def resource_response(response: aiohttp.ClientResponse) -> StreamingResponse:
    return ResourceStreamingResponse(response)


async def stream_resource(response: aiohttp.ClientResponse) -> AsyncIterator[bytes]:
    try:
        async for chunk in response.content.iter_chunked(STREAM_CHUNK_BYTES):
            yield chunk
    finally:
        response.close()


async def close_resource(response: aiohttp.ClientResponse) -> None:
    response.close()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    resolver = PublicAddressResolver()
    connector = aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False)
    try:
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=UPSTREAM_TIMEOUT_SECONDS),
            auto_decompress=False,
            cookie_jar=aiohttp.DummyCookieJar(),
            trust_env=False,
        ) as session:
            application.state.upstream_client = UpstreamClient(session)
            yield
    finally:
        await resolver.close()


def get_upstream_client(request: Request) -> UpstreamClient:
    return request.app.state.upstream_client
