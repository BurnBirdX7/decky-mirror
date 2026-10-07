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
    from decky_mirror import main
    from decky_mirror.upstream import UpstreamClient, get_upstream_client

from decky_mirror.catalogue import encode_resource_url
from decky_mirror.resource_signing import sign_resource_token
from decky_mirror.security import BlockedAddressLookupError


def signed_resource_token(url):
    return sign_resource_token(encode_resource_url(url))


class ApiTests(unittest.TestCase):
    def setUp(self):
        main.limiter.reset()
        self.session = FakeSession()
        main.app.dependency_overrides[get_upstream_client] = lambda: UpstreamClient(self.session, http_version="1.1")
        self.client = self.enterContext(TestClient(main.app))
        self.addCleanup(main.app.dependency_overrides.clear)

    def test_home_shows_version_and_links_without_upstream_or_rate_limit(self):
        for _ in range(6):
            response = self.client.get("/")
            self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Decky Mirror " + main.constants.VERSION, response.text)
        self.assertNotIn("{{VERSION}}", response.text)
        for link in ("https://github.com/BurnBirdX7/decky-mirror", "/docs", "/plugins"):
            self.assertIn(f'href="{link}"', response.text)
        schema = self.client.get("/openapi.json").json()
        self.assertEqual(schema["info"]["version"], main.constants.VERSION)
        self.assertNotIn("/", schema["paths"])
        self.assertEqual(self.session.requests, [])

    def test_unsigned_and_tampered_tokens_are_rejected_without_upstream_request(self):
        token = encode_resource_url(IMAGE_URL)
        signed = sign_resource_token(token)
        signature = signed.split(".")[1]
        changed_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
        invalid_tokens = (
            token,
            token + "." + changed_signature,
            encode_resource_url(ARTIFACT_URL) + "." + signature,
            signed + ".extra",
            signed + "=",
            token + ".short",
            "A." + signature,
        )
        for invalid in invalid_tokens:
            with self.subTest(token=invalid):
                response = self.client.get("/resources/base64/" + invalid)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {"detail": "Invalid resource signature"})
        self.assertEqual(self.session.requests, [])

    def test_signed_url_preserves_unicode_escaping_and_query(self):
        url = "https://images.example/тест.png?value=%2f&value=a+b&empty="
        self.session.results.append(FakeResponse(b"image"))
        response = self.client.get("/resources/base64/" + signed_resource_token(url))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(self.session.requests[0].url), url)

    def test_catalogue_substitutes_resource_routes_and_preserves_metadata(self):
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
            "https://mirror.example/resources/base64/" + signed_resource_token(ARTIFACT_URL),
        )
        self.assertEqual(
            plugin["image_url"],
            "https://mirror.example/resources/base64/" + signed_resource_token(IMAGE_URL),
        )
        self.assertEqual(plugin["unknown_field"], {"preserved": True})
        self.assertEqual(self.session.requests[0].url.query.getall("tags"), ["one", "two,three"])

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
            "https://cdn.example/file/steam-deck-homebrew/versions/" + ARCHIVE_HASH + ".zip",
        )
        self.assertTrue(reply.closed)

    def test_base64_image_uses_exact_upstream_url(self):
        self.session.results.append(FakeResponse(b"PNG", headers={"Content-Type": "image/png"}))
        response = self.client.get("/resources/base64/" + signed_resource_token(IMAGE_URL))
        self.assertEqual(response.content, b"PNG")
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(str(self.session.requests[0].url), IMAGE_URL)

    def test_resource_upstream_error_status_and_body_are_preserved(self):
        self.session.results.append(FakeResponse(b"not found", 404, {"Content-Type": "text/plain"}))
        response = self.client.get("/resources/base64/" + signed_resource_token(ARTIFACT_URL))
        self.assertEqual((response.status_code, response.content), (404, b"not found"))
        self.assertEqual(str(self.session.requests[0].url), ARTIFACT_URL)

    def test_install_statistics_preserve_success_and_error_responses(self):
        for status in (200, 404, 429):
            with self.subTest(status=status):
                self.session.results.append(FakeResponse(status=status, headers={"Retry-After": "42"}))
                response = self.client.post("/plugins/Test%20Plugin/versions/1.0.0/increment?isUpdate=false")
                self.assertEqual((response.status_code, response.content), (status, b""))
                self.assertEqual(response.headers["retry-after"], "42")
                self.assertEqual(self.session.requests[-1].url.query["isUpdate"], "false")

    def test_invalid_resources_return_bad_request_without_upstream_request(self):
        for path in (
            "/resources/hash/bad",
            "/resources/base64/" + sign_resource_token("A"),
            "/resources/base64/" + signed_resource_token("file:///etc/passwd"),
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 400)
        self.assertEqual(self.session.requests, [])

    def test_non_public_resources_return_forbidden_without_contacting_target(self):
        for url in (
            "http://127.0.0.1/",
            "http://10.0.0.1/",
            "http://[::1]/",
        ):
            with self.subTest(url=url):
                response = self.client.get("/resources/base64/" + signed_resource_token(url))
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.session.requests, [])

    def test_private_dns_error_returns_forbidden(self):
        key = SimpleNamespace(host="private.example", port=443, ssl=True)
        self.session.results.append(aiohttp.ClientConnectorDNSError(key, BlockedAddressLookupError("private")))
        response = self.client.get("/resources/base64/" + signed_resource_token("https://private.example/resource"))
        self.assertEqual(response.status_code, 403)

    def test_localhost_is_rejected_by_resolver_not_surface_check(self):
        key = SimpleNamespace(host="localhost", port=80, ssl=False)
        self.session.results.append(aiohttp.ClientConnectorDNSError(key, BlockedAddressLookupError("loopback")))
        response = self.client.get("/resources/base64/" + signed_resource_token("http://localhost/"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(self.session.requests), 1)

    def test_private_redirect_returns_forbidden_and_is_not_followed(self):
        self.session.results.append(FakeResponse(status=302, headers={"Location": "http://127.0.0.1/"}))
        response = self.client.get("/resources/base64/" + signed_resource_token(ARTIFACT_URL))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(self.session.requests), 1)

    def test_eleventh_redirect_returns_bad_gateway(self):
        self.session.results.extend(FakeResponse(status=302, headers={"Location": "/next"}) for _ in range(11))
        response = self.client.get("/resources/base64/" + signed_resource_token(ARTIFACT_URL))
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
        self.assertEqual(response.headers["access-control-allow-origin"], headers["Origin"])
        response = self.client.get("/resources/hash/bad", headers={"Origin": headers["Origin"]})
        self.assertEqual(response.headers["access-control-allow-origin"], headers["Origin"])
        self.assertEqual(self.session.requests, [])

    def test_all_handlers_limit_repeated_requests_before_contacting_upstream(self):
        cases = (
            ("GET", "/plugins", lambda: FakeResponse.catalogue([])),
            ("POST", "/plugins/Test/versions/1/increment", FakeResponse),
            ("GET", "/resources/hash/" + ARCHIVE_HASH, FakeResponse),
            ("GET", "/resources/base64/" + signed_resource_token(IMAGE_URL), FakeResponse),
        )
        with patch("limits.storage.memory.time.time", return_value=1000):
            for method, path, reply in cases:
                with self.subTest(path=path):
                    main.limiter.reset()
                    self.session.results.extend(reply() for _ in range(5))
                    before = len(self.session.requests)
                    for _ in range(5):
                        self.assertEqual(self.client.request(method, path).status_code, 200)
                    response = self.client.request(method, path)
                    self.assertEqual(response.status_code, 429)
                    self.assertIn("error", response.json())
                    self.assertEqual(len(self.session.requests), before + 5)

    def test_limit_resets_after_window_expires(self):
        with patch("limits.storage.memory.time.time", return_value=1000) as clock:
            self.session.results.extend(FakeResponse.catalogue([]) for _ in range(6))
            for _ in range(5):
                self.assertEqual(self.client.get("/plugins").status_code, 200)
            self.assertEqual(self.client.get("/plugins").status_code, 429)
            clock.return_value = 1001.01
            self.assertEqual(self.client.get("/plugins").status_code, 200)
            self.assertEqual(len(self.session.requests), 6)

    def test_query_parameters_share_the_same_quota(self):
        paths = (
            "/plugins?query=filter",
            "/resources/base64/" + signed_resource_token(IMAGE_URL) + "?ignored=value",
        )
        with patch("limits.storage.memory.time.time", return_value=1000):
            for path in paths:
                with self.subTest(path=path):
                    main.limiter.reset()
                    before = len(self.session.requests)
                    for index in range(5):
                        self.session.results.append(FakeResponse.catalogue([]))
                        self.assertEqual(self.client.get(path + str(index)).status_code, 200)
                    self.assertEqual(self.client.get(path.split("?")[0]).status_code, 429)
                    self.assertEqual(len(self.session.requests), before + 5)

    def test_different_client_ips_have_independent_quotas(self):
        with patch("limits.storage.memory.time.time", return_value=1000):
            self.session.results.extend(FakeResponse.catalogue([]) for _ in range(6))
            for _ in range(5):
                self.assertEqual(self.client.get("/plugins").status_code, 200)
            self.assertEqual(self.client.get("/plugins").status_code, 429)
            with TestClient(main.app, client=("192.0.2.2", 12345)) as other_client:
                self.assertEqual(other_client.get("/plugins").status_code, 200)
            self.assertEqual(len(self.session.requests), 6)

    def test_many_resource_paths_have_independent_quotas(self):
        with patch("limits.storage.memory.time.time", return_value=1000):
            for index in range(205):
                self.session.results.append(FakeResponse(b"image"))
                token = signed_resource_token(f"https://images.example/{index}.png")
                self.assertEqual(self.client.get("/resources/base64/" + token).status_code, 200)
            self.assertEqual(len(self.session.requests), 205)

    def test_rate_limit_response_preserves_cors_headers(self):
        with patch("limits.storage.memory.time.time", return_value=1000):
            self.session.results.extend(FakeResponse.catalogue([]) for _ in range(5))
            for _ in range(5):
                self.client.get("/plugins")
            response = self.client.get("/plugins", headers={"Origin": "https://steamloopback.host"})
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.headers["access-control-allow-origin"], "https://steamloopback.host")
            self.assertEqual(len(self.session.requests), 5)
