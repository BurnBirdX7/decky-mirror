import asyncio
import json
from collections import deque
from dataclasses import dataclass

from multidict import CIMultiDict
from yarl import URL

ARCHIVE_HASH = "a" * 64
IMAGE_URL = "https://images.example/thumb.png?size=320"
ARTIFACT_URL = "https://downloads.example/custom.zip?signature=a%2Bb&path=x%2Fy&empty="
TEST_ENVIRONMENT = {
    "DOMAIN": "mirror.example",
    "TARGET_STORE_DOMAIN": "store.example",
    "TARGET_CDN_DOMAIN": "cdn.example",
}


def plugin_catalogue(versions=None):
    return [
        {
            "id": 1,
            "name": "Test Plugin",
            "author": "Tester",
            "description": "Test plugin",
            "tags": ["test"],
            "image_url": IMAGE_URL,
            "visible": True,
            "versions": versions if versions is not None else [{"name": "1.0.0", "hash": ARCHIVE_HASH}],
            "unknown_field": {"preserved": True},
        }
    ]


class FakeContent:
    def __init__(self, content, error=None):
        self.content = content
        self.error = error

    async def iter_chunked(self, chunk_size):
        for offset in range(0, len(self.content), min(chunk_size, 3)):
            yield self.content[offset : offset + min(chunk_size, 3)]
        if self.error is not None:
            raise self.error


class FakeResponse:
    def __init__(self, content=b"", status=200, headers=None, read_error=None, stream_error=None):
        self.status = status
        self.headers = CIMultiDict(headers or {})
        self.body = content
        self.content = FakeContent(content, stream_error)
        self.read_error = read_error
        self.url = URL("https://public.example/")
        self.closed = False
        self.close_calls = 0

    @classmethod
    def catalogue(cls, plugins):
        return cls(json.dumps(plugins).encode(), headers={"Content-Type": "application/json"})

    async def read(self):
        if self.read_error is not None:
            raise self.read_error
        return self.body

    def close(self):
        self.closed = True
        self.close_calls += 1


class FakeRequestContext:
    def __init__(self, result):
        self.result = result

    def __await__(self):
        return self.__aenter__().__await__()

    async def __aenter__(self):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def __aexit__(self, *arguments):
        self.result.close()


@dataclass
class RecordedRequest:
    method: str
    url: URL
    options: dict


class FakeSession:
    def __init__(self, *results):
        self.results = deque(results)
        self.requests = []

    def request(self, method, url, **options):
        self.requests.append(RecordedRequest(method, url, options))
        result = self.results.popleft()
        if isinstance(result, FakeResponse):
            result.url = url
        return FakeRequestContext(result)


async def call_response(response, send):
    async def receive():
        await asyncio.Event().wait()

    scope = {
        "type": "http",
        "method": "GET",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
    }
    await response(scope, receive, send)


async def render_response(response):
    messages = []

    async def send(message):
        messages.append(message)

    await call_response(response, send)
    return b"".join(message.get("body", b"") for message in messages)
