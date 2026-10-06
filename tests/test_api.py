import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import aiohttp
from fastapi.testclient import TestClient

from tests.support import (
    ARCHIVE_HASH,
    ARTIFACT_URL,
    IMAGE_URL,
    TEST_ENVIRONMENT,
    FakeResponse,
    FakeSession,
    plugin_catalogue,
)

with patch.dict(os.environ, TEST_ENVIRONMENT):
    import main
    from upstream import UpstreamClient, get_upstream_client

from catalogue import encode_resource_url
from security import BlockedAddressLookupError


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        main.app.dependency_overrides[get_upstream_client] = lambda: UpstreamClient(
            self.session
        )
        self.client = self.enterContext(TestClient(main.app))
        self.addCleanup(main.app.dependency_overrides.clear)

    def test_catalogue_rewrites_resource_routes_and_preserves_metadata(self):
        self.session.results.append(
            FakeResponse.catalogue(
                plugin_catalogue(
                    [
                        {"name": "2", "hash": ARCHIVE_HASH},
                        {"name": "1", "hash": "b" * 64, "artifact": ARTIFACT_URL},
                    ]
                )
            )
        )
        response = self.client.get(
            "/plugins",
            params=[("tags", "one"), ("tags", "two,three")],
            headers={"X-Decky-Version": "3.2.0"},
        )
        self.assertEqual(response.status_code, 200)
        plugin = response.json()[0]
        self.assertEqual(
            plugin["versions"][0]["artifact"],
            "https://mirror.example/resources/hash/" + ARCHIVE_HASH,
        )
        self.assertEqual(
            plugin["versions"][1]["artifact"],
            "https://mirror.example/resources/base64/" + encode_resource_url(ARTIFACT_URL),
        )
        self.assertEqual(
            plugin["image_url"],
            "https://mirror.example/resources/base64/" + encode_resource_url(IMAGE_URL),
        )
        self.assertEqual(plugin["unknown_field"], {"preserved": True})
        self.assertEqual(
            self.session.requests[0].url.query.getall("tags"), ["one", "two,three"]
        )

    def test_query_defaults_and_validation_match_store_contract(self):
        self.session.results.append(FakeResponse.catalogue([]))
        self.assertEqual(self.client.get("/plugins").status_code, 200)
        self.assertEqual(self.session.requests[0].url.query["hidden"], "false")
        self.assertEqual(self.session.requests[0].url.query["sort_direction"], "desc")
        self.assertNotIn("sort_by", self.session.requests[0].url.query)
        self.assertEqual(self.client.get("/plugins?sort_by=invalid").status_code, 422)
        self.assertEqual(len(self.session.requests), 1)

    def test_hash_resource_uses_documented_cdn_path_and_streams_archive(self):
        archive = b"PK\x03\x04unchanged"
        reply = FakeResponse(
            archive,
            headers={
                "Content-Type": "application/zip",
                "Content-Length": str(len(archive)),
            },
        )
        self.session.results.append(reply)
        response = self.client.get("/resources/hash/" + ARCHIVE_HASH)
        self.assertEqual(response.content, archive)
        self.assertEqual(
            str(self.session.requests[0].url),
            "https://cdn.example/file/steam-deck-homebrew/versions/"
            + ARCHIVE_HASH
            + ".zip",
        )
        self.assertTrue(reply.closed)

    def test_base64_image_uses_exact_upstream_url(self):
        self.session.results.append(
            FakeResponse(b"PNG", headers={"Content-Type": "image/png"})
        )
        response = self.client.get("/resources/base64/" + encode_resource_url(IMAGE_URL))
        self.assertEqual(response.content, b"PNG")
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(str(self.session.requests[0].url), IMAGE_URL)

    def test_resource_upstream_error_status_and_body_are_preserved(self):
        self.session.results.append(
            FakeResponse(b"not found", 404, {"Content-Type": "text/plain"})
        )
        response = self.client.get("/resources/base64/" + encode_resource_url(ARTIFACT_URL))
        self.assertEqual((response.status_code, response.content), (404, b"not found"))
        self.assertEqual(str(self.session.requests[0].url), ARTIFACT_URL)

    def test_install_statistics_preserve_success_and_error_responses(self):
        for status in (200, 404, 429):
            with self.subTest(status=status):
                self.session.results.append(
                    FakeResponse(status=status, headers={"Retry-After": "42"})
                )
                response = self.client.post(
                    "/plugins/Test%20Plugin/versions/1.0.0/increment?isUpdate=false"
                )
                self.assertEqual(
                    (response.status_code, response.content), (status, b"")
                )
                self.assertEqual(response.headers["retry-after"], "42")
                self.assertEqual(
                    self.session.requests[-1].url.query["isUpdate"], "false"
                )

    def test_invalid_resources_return_bad_request_without_upstream_request(self):
        for path in (
            "/resources/hash/bad",
            "/resources/base64/A",
            "/resources/base64/" + encode_resource_url("file:///etc/passwd"),
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 400)
        self.assertEqual(self.session.requests, [])

    def test_non_public_resources_return_forbidden_without_contacting_target(self):
        for url in (
            "http://localhost/",
            "http://127.0.0.1/",
            "http://10.0.0.1/",
            "http://[::1]/",
        ):
            with self.subTest(url=url):
                response = self.client.get("/resources/base64/" + encode_resource_url(url))
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.session.requests, [])

    def test_private_dns_error_returns_forbidden(self):
        key = SimpleNamespace(host="private.example", port=443, ssl=True)
        self.session.results.append(
            aiohttp.ClientConnectorDNSError(key, BlockedAddressLookupError("private"))
        )
        response = self.client.get(
            "/resources/base64/" + encode_resource_url("https://private.example/resource")
        )
        self.assertEqual(response.status_code, 403)

    def test_private_redirect_returns_forbidden_and_is_not_followed(self):
        self.session.results.append(
            FakeResponse(status=302, headers={"Location": "http://127.0.0.1/"})
        )
        response = self.client.get("/resources/base64/" + encode_resource_url(ARTIFACT_URL))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(self.session.requests), 1)

    def test_eleventh_redirect_returns_bad_gateway(self):
        self.session.results.extend(
            FakeResponse(status=302, headers={"Location": "/next"}) for _ in range(11)
        )
        response = self.client.get("/resources/base64/" + encode_resource_url(ARTIFACT_URL))
        self.assertEqual(response.status_code, 502)
        self.assertEqual(len(self.session.requests), 11)

    def test_bad_catalogue_and_upstream_timeout_are_reported(self):
        self.session.results.append(
            FakeResponse.catalogue(
                plugin_catalogue(
                    [
                        {"name": "1", "hash": ARCHIVE_HASH, "artifact": ""},
                    ]
                )
            )
        )
        self.assertEqual(self.client.get("/plugins").status_code, 502)
        self.session.results.append(TimeoutError())
        self.assertEqual(self.client.get("/plugins").status_code, 504)

    def test_cors_preflight_and_error_response_headers_are_preserved(self):
        headers = {
            "Origin": "https://steamloopback.host",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Decky-Version",
        }
        response = self.client.options("/plugins", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"], headers["Origin"]
        )
        response = self.client.get(
            "/resources/hash/bad", headers={"Origin": headers["Origin"]}
        )
        self.assertEqual(
            response.headers["access-control-allow-origin"], headers["Origin"]
        )
        self.assertEqual(self.session.requests, [])
