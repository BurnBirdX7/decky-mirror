import asyncio
import gzip
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
from aiohttp.resolver import ThreadedResolver
from fastapi import FastAPI
from starlette.requests import ClientDisconnect, Request
from yarl import URL

from tests.support import (
    TEST_ENVIRONMENT,
    FakeResponse,
    FakeSession,
    call_response,
    render_response,
)

with patch.dict(os.environ, TEST_ENVIRONMENT):
    from decky_mirror import constants
    from decky_mirror.upstream import ResourceStreamingResponse, UpstreamClient, get_upstream_client, lifespan

from decky_mirror.errors import (
    BlockedDestinationError,
    InvalidResourceError,
    RedirectLimitError,
    UpstreamRequestError,
    UpstreamTimeoutError,
)
from decky_mirror.security import BlockedAddressLookupError, PublicAddressResolver


class UpstreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalogue_forwards_query_parameters_and_version_header(self):
        session = FakeSession(FakeResponse(b"[]"))
        parameters = {
            "query": "test",
            "tags": ["one", "two,three"],
            "hidden": "true",
            "sort_by": "date",
            "sort_direction": "asc",
        }
        await UpstreamClient(session, http_version="1.1").get_catalogue(parameters, "3.2.0")
        request = session.requests[0]
        self.assertEqual(request.url.host, "store.example")
        self.assertEqual(request.url.query.getall("tags"), ["one", "two,three"])
        self.assertEqual(request.options["headers"], {"X-Decky-Version": "3.2.0", "Via": "1.1 mirror.example"})
        self.assertFalse(request.options["allow_redirects"])

    async def test_increment_encodes_names_and_forwards_boolean(self):
        session = FakeSession(FakeResponse(status=200))
        await UpstreamClient(session, http_version="1.1").post_install_increment("Plugin & тест", "1.0+test", False)
        request = session.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertIn("Plugin%20%26%20%D1%82%D0%B5%D1%81%D1%82", request.url.raw_path)
        self.assertIn("1.0%2Btest", request.url.raw_path)
        self.assertEqual(request.url.query["isUpdate"], "false")
        self.assertNotIn("data", request.options)

    async def test_store_status_body_and_retry_header_are_preserved(self):
        reply = FakeResponse(
            b"rate limited",
            429,
            {"Retry-After": "42", "Content-Type": "text/plain", "Connection": "close"},
        )
        response = await UpstreamClient(FakeSession(reply), http_version="1.1").post_install_increment("Test", "1", True)
        self.assertEqual((response.status, response.content), (429, b"rate limited"))
        self.assertEqual(response.headers["retry-after"], "42")
        self.assertNotIn("connection", response.headers)
        self.assertTrue(reply.closed)

    async def test_resource_content_encoding_headers_and_bytes_are_preserved(self):
        content = gzip.compress(b"resource bytes", mtime=0)
        reply = FakeResponse(
            content,
            headers={
                "Content-Encoding": "gzip",
                "Content-Length": str(len(content)),
                "Content-Type": "application/zip",
            },
        )
        result = await UpstreamClient(FakeSession(reply), http_version="1.1").get_resource_with_redirects(URL("https://cdn.example/archive"))
        response = ResourceStreamingResponse(result)
        body = await render_response(response)
        self.assertEqual(body, content)
        self.assertEqual(response.headers["content-encoding"], "gzip")
        self.assertEqual(response.headers["content-length"], str(len(content)))
        self.assertTrue(reply.closed)

    async def test_relative_and_cross_host_public_redirects_are_followed(self):
        first = FakeResponse(status=302, headers={"Location": "../next?token=a%2Bb"})
        second = FakeResponse(status=307, headers={"Location": "https://other.example/final"})
        final = FakeResponse(b"done")
        session = FakeSession(first, second, final)
        result = await UpstreamClient(session, http_version="1.1").get_resource_with_redirects(URL("https://cdn.example/path/start"))
        self.assertIs(result, final)
        self.assertEqual(str(session.requests[1].url), "https://cdn.example/next?token=a%2Bb")
        self.assertEqual(session.requests[2].url.host, "other.example")
        self.assertTrue(first.closed and second.closed)
        final.close()

    async def test_ten_redirects_succeed(self):
        redirects = [FakeResponse(status=302, headers={"Location": f"/step/{index}"}) for index in range(10)]
        final = FakeResponse(b"done")
        session = FakeSession(*redirects, final)
        self.assertIs(
            await UpstreamClient(session, http_version="1.1").get_resource_with_redirects(URL("https://cdn.example/start")),
            final,
        )
        self.assertEqual(len(session.requests), 11)
        self.assertTrue(all(reply.closed for reply in redirects))
        final.close()

    async def test_eleventh_redirect_is_rejected_and_closed(self):
        redirects = [FakeResponse(status=302, headers={"Location": f"/step/{index}"}) for index in range(11)]
        session = FakeSession(*redirects)
        with self.assertRaises(RedirectLimitError):
            await UpstreamClient(session, http_version="1.1").get_resource_with_redirects(URL("https://cdn.example/start"))
        self.assertEqual(len(session.requests), 11)
        self.assertTrue(all(reply.closed for reply in redirects))

    async def test_private_redirect_is_blocked_before_requesting_target(self):
        reply = FakeResponse(status=302, headers={"Location": "http://169.254.169.254/metadata"})
        session = FakeSession(reply)
        with self.assertRaises(BlockedDestinationError):
            await UpstreamClient(session, http_version="1.1").get_resource_with_redirects(URL("https://cdn.example/start"))
        self.assertEqual(len(session.requests), 1)
        self.assertTrue(reply.closed)

    async def test_private_literal_is_blocked_before_any_request(self):
        session = FakeSession()
        with self.assertRaises(BlockedDestinationError):
            await UpstreamClient(session, http_version="1.1").get_resource_with_redirects(URL("http://127.0.0.1/private"))
        self.assertEqual(session.requests, [])

    async def test_wrapped_dns_block_is_forbidden_not_bad_gateway(self):
        key = SimpleNamespace(host="blocked.example", port=443, ssl=True)
        error = aiohttp.ClientConnectorDNSError(key, BlockedAddressLookupError("private address"))
        with self.assertRaises(BlockedDestinationError):
            await UpstreamClient(FakeSession(error), http_version="1.1").get_resource_with_redirects(URL("https://blocked.example/resource"))

    async def test_real_connector_blocks_private_dns_without_opening_socket(self):
        resolver = PublicAddressResolver()
        socket_factory = Mock(side_effect=AssertionError("Blocked destination must not be contacted"))
        connector = aiohttp.TCPConnector(resolver=resolver, socket_factory=socket_factory, use_dns_cache=False)
        try:
            async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
                with (
                    patch.object(
                        ThreadedResolver,
                        "resolve",
                        AsyncMock(return_value=[{"host": "127.0.0.1"}]),
                    ),
                    self.assertRaises(BlockedDestinationError),
                ):
                    await UpstreamClient(session, http_version="1.1").get_resource_with_redirects(URL("https://blocked.example/resource"))
            socket_factory.assert_not_called()
        finally:
            await resolver.close()

    async def test_timeout_and_connection_failure_are_distinct(self):
        cases = [
            (TimeoutError(), UpstreamTimeoutError),
            (aiohttp.ClientConnectionError(), UpstreamRequestError),
        ]
        for error, expected in cases:
            with self.subTest(error=type(error).__name__), self.assertRaises(expected):
                await UpstreamClient(FakeSession(error), http_version="1.1").get_resource_with_redirects(URL("https://cdn.example/resource"))

    async def test_buffered_read_failure_closes_response(self):
        reply = FakeResponse(read_error=TimeoutError())
        with self.assertRaises(UpstreamTimeoutError):
            await UpstreamClient(FakeSession(reply), http_version="1.1").get_catalogue({}, None)
        self.assertTrue(reply.closed)

    async def test_redirect_without_location_is_rejected_and_closed(self):
        reply = FakeResponse(status=302)
        with self.assertRaises(UpstreamRequestError):
            await UpstreamClient(FakeSession(reply), http_version="1.1").get_resource_with_redirects(URL("https://cdn.example/resource"))
        self.assertTrue(reply.closed)

    async def test_stream_failure_closes_response_once(self):
        reply = FakeResponse(b"partial", stream_error=aiohttp.ClientPayloadError())
        with self.assertRaises(aiohttp.ClientPayloadError):
            await render_response(ResourceStreamingResponse(reply))
        self.assertEqual(reply.close_calls, 1)

    async def test_failure_before_body_closes_response_once(self):
        reply = FakeResponse(b"unread")

        async def send(message):
            raise OSError("Client disconnected before response headers")

        with self.assertRaises(ClientDisconnect):
            await call_response(ResourceStreamingResponse(reply), send)
        self.assertEqual(reply.close_calls, 1)

    async def test_response_completion_closes_response_once(self):
        reply = FakeResponse(b"complete")
        self.assertEqual(await render_response(ResourceStreamingResponse(reply)), b"complete")
        self.assertEqual(reply.close_calls, 1)

    async def test_lifespan_closes_shared_session_on_shutdown(self):
        application = FastAPI()
        async with lifespan(application):
            session = application.state.upstream_session
            self.assertFalse(session.closed)
            self.assertEqual(
                session.headers["User-Agent"], f"decky-mirror/{constants.VERSION} (+https://mirror.example/)"
            )
        self.assertTrue(session.closed)

    async def test_request_clients_share_session_and_use_received_http_version(self):
        application = FastAPI()
        session = FakeSession()
        application.state.upstream_session = session
        for version in ("1.1", "2"):
            with self.subTest(version=version):
                request = Request(
                    {
                        "type": "http",
                        "http_version": version,
                        "app": application,
                        "client": ("192.0.2.1", 12345),
                        "headers": [
                            (b"via", b"1.0 untrusted"),
                            (b"user-agent", b"untrusted"),
                            (b"forwarded", b"for=192.0.2.1"),
                            (b"x-forwarded-for", b"192.0.2.1"),
                        ],
                    }
                )
                client = get_upstream_client(request)
                self.assertIs(client.session, session)
                session.results.extend(
                    (
                        FakeResponse(b"[]"),
                        FakeResponse(),
                        FakeResponse(status=302, headers={"Location": "https://other.example/final"}),
                        FakeResponse(),
                    )
                )
                before = len(session.requests)
                await client.get_catalogue({}, "3.2.0")
                await client.post_install_increment("Plugin", "1", True)
                response = await client.get_resource_with_redirects(URL("https://cdn.example/start"))
                response.close()
                forwarded = session.requests[before:]
                self.assertEqual(len(forwarded), 4)
                for outgoing in forwarded:
                    headers = outgoing.options["headers"]
                    self.assertEqual(headers["Via"], f"{version} mirror.example")
                    self.assertFalse(
                        {name.lower() for name in headers} & {"forwarded", "x-forwarded-for", "user-agent"}
                    )
                self.assertEqual(forwarded[0].options["headers"]["X-Decky-Version"], "3.2.0")

    async def test_asgi_disconnect_closes_response_once(self):
        reply = FakeResponse(b"several chunks")
        response = ResourceStreamingResponse(reply)

        async def receive():
            await asyncio.Event().wait()

        async def send(message):
            if message["type"] == "http.response.body":
                raise OSError("Client disconnected")

        scope = {
            "type": "http",
            "method": "GET",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
        }
        with self.assertRaises(ClientDisconnect):
            await response(scope, receive, send)
        self.assertEqual(reply.close_calls, 1)

    async def test_redirect_with_invalid_raw_text_is_not_followed(self):
        reply = FakeResponse(status=302, headers={"Location": "\nhttps://cdn.example/next"})
        session = FakeSession(reply)
        with self.assertRaises(InvalidResourceError):
            await UpstreamClient(session, http_version="1.1").get_resource_with_redirects(URL("https://cdn.example/start"))
        self.assertEqual(len(session.requests), 1)
        self.assertTrue(reply.closed)

    async def test_asgi_cancellation_closes_response_once(self):
        reply = FakeResponse(b"streamed bytes")

        async def send(message):
            if message["type"] == "http.response.body":
                raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            await call_response(ResourceStreamingResponse(reply), send)
        self.assertEqual(reply.close_calls, 1)
