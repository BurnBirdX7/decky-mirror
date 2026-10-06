import copy
import json
import unittest

from catalogue import (
    decode_resource_url,
    encode_resource_url,
    substitute_catalogue_resource_urls,
)
from errors import InvalidCatalogueError, InvalidResourceError
from tests.support import ARCHIVE_HASH, ARTIFACT_URL, IMAGE_URL, plugin_catalogue


class CatalogueTests(unittest.TestCase):
    def substitute(self, catalogue):
        return substitute_catalogue_resource_urls(json.dumps(catalogue).encode(), "mirror.example")

    def test_missing_and_null_artifacts_use_hash_routes(self):
        versions = [
            {"name": "2.0.0", "hash": ARCHIVE_HASH},
            {"name": "1.0.0", "hash": "b" * 64, "artifact": None},
        ]
        substituted = self.substitute(plugin_catalogue(versions))[0]["versions"]
        self.assertEqual(
            substituted[0]["artifact"],
            "https://mirror.example/resources/hash/" + ARCHIVE_HASH,
        )
        self.assertEqual(
            substituted[1]["artifact"],
            "https://mirror.example/resources/hash/" + "b" * 64,
        )

    def test_explicit_artifact_and_image_use_complete_encoded_urls(self):
        version = {"name": "1.0.0", "hash": ARCHIVE_HASH, "artifact": ARTIFACT_URL}
        substituted = self.substitute(plugin_catalogue([version]))[0]
        self.assertEqual(
            substituted["versions"][0]["artifact"],
            "https://mirror.example/resources/base64/" + encode_resource_url(ARTIFACT_URL),
        )
        self.assertEqual(
            substituted["image_url"],
            "https://mirror.example/resources/base64/" + encode_resource_url(IMAGE_URL),
        )

    def test_substitution_preserves_fields_hashes_order_and_original_input(self):
        original = plugin_catalogue(
            [
                {"name": "3.0.0", "hash": "c" * 64, "extra": 42},
                {"name": "1.0.0", "hash": ARCHIVE_HASH},
            ]
        )
        unchanged = copy.deepcopy(original)
        substituted = self.substitute(original)[0]
        self.assertEqual(original, unchanged)
        self.assertEqual(substituted["unknown_field"], original[0]["unknown_field"])
        self.assertEqual(
            [version["hash"] for version in substituted["versions"]],
            ["c" * 64, ARCHIVE_HASH],
        )
        self.assertEqual(substituted["versions"][0]["extra"], 42)

    def test_url_round_trip_preserves_utf8_escapes_and_query(self):
        urls = [
            ARTIFACT_URL,
            "https://images.example/тест.png?value=%2f&value=a+b#fragment",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(str(decode_resource_url(encode_resource_url(url))), url)
                self.assertEqual(len(encode_resource_url(url)) % 4, 0)

    def test_invalid_catalogue_content_is_rejected(self):
        invalid = [b"not json", b"{}", b"[null]", b'[{"versions":null}]']
        for content in invalid:
            with (
                self.subTest(content=content),
                self.assertRaises(InvalidCatalogueError),
            ):
                substitute_catalogue_resource_urls(content, "mirror.example")

    def test_empty_artifacts_and_invalid_image_urls_are_rejected(self):
        for artifact in ("", "ftp://downloads.example/file", 123):
            with (
                self.subTest(artifact=artifact),
                self.assertRaises(InvalidCatalogueError),
            ):
                self.substitute(plugin_catalogue([{"name": "1", "hash": ARCHIVE_HASH, "artifact": artifact}]))
        catalogue = plugin_catalogue()
        catalogue[0]["image_url"] = ""
        with self.assertRaises(InvalidCatalogueError):
            self.substitute(catalogue)

    def test_invalid_resource_tokens_are_rejected(self):
        tokens = ["", "A", "%%", "a=", "_w", "aHR0cHM6Ly9wdWJsaWMuZXhhbXBsZS9hZ"]
        for token in tokens:
            with self.subTest(token=token), self.assertRaises(InvalidResourceError):
                decode_resource_url(token)

    def test_unsupported_and_credentialled_urls_are_rejected(self):
        urls = [
            "file:///etc/passwd",
            "relative/path",
            "https://user:pass@example.com/",
            "https://public.example/a\n",
            "https://public.example/\x00",
        ]
        for url in urls:
            with self.subTest(url=url), self.assertRaises(InvalidResourceError):
                decode_resource_url(encode_resource_url(url))

    def test_encoding_retains_required_padding(self):
        self.assertTrue(encode_resource_url("https://example.com/").endswith("="))
        self.assertTrue(encode_resource_url("https://example.com/ab").endswith("=="))

    def test_unpadded_tokens_are_not_repaired(self):
        token = encode_resource_url("https://example.com/")
        with self.assertRaises(InvalidResourceError):
            decode_resource_url(token.rstrip("="))

    def test_malformed_padding_and_alphabet_are_rejected(self):
        token = encode_resource_url("https://example.com/")
        tokens = [token + "=", "=" + token, token + "!", token[:-1], "////", "abcd=efg"]
        for malformed in tokens:
            with self.subTest(token=malformed), self.assertRaises(InvalidResourceError):
                decode_resource_url(malformed)

    def test_non_public_hosts_pass_decode_and_url_validation(self):
        for url in (
            "http://localhost/",
            "http://127.0.0.1/",
            "http://10.0.0.1/",
            "http://[::1]/",
        ):
            with self.subTest(url=url):
                self.assertEqual(str(decode_resource_url(encode_resource_url(url))), url)

    def test_invalid_utf8_after_base64_decoding_is_rejected(self):
        with self.assertRaises(InvalidResourceError):
            decode_resource_url("_w==")

    def test_decode_does_not_require_canonical_reencoding(self):
        self.assertEqual(
            str(decode_resource_url("aHR0cHM6Ly9leGFtcGxlLmNvbS9=")),
            "https://example.com/",
        )
