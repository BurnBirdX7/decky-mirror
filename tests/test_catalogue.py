import copy
import json
import unittest

from catalogue import decode_resource_url, encode_resource_url, rewrite_catalogue
from errors import InvalidCatalogueError, InvalidResourceError
from tests.support import ARCHIVE_HASH, ARTIFACT_URL, IMAGE_URL, plugin_catalogue


class CatalogueTests(unittest.TestCase):
    def rewrite(self, catalogue):
        return rewrite_catalogue(json.dumps(catalogue).encode(), "mirror.example")

    def test_missing_and_null_artifacts_use_hash_routes(self):
        versions = [
            {"name": "2.0.0", "hash": ARCHIVE_HASH},
            {"name": "1.0.0", "hash": "b" * 64, "artifact": None},
        ]
        rewritten = self.rewrite(plugin_catalogue(versions))[0]["versions"]
        self.assertEqual(
            rewritten[0]["artifact"],
            "https://mirror.example/resources/hash/" + ARCHIVE_HASH,
        )
        self.assertEqual(
            rewritten[1]["artifact"],
            "https://mirror.example/resources/hash/" + "b" * 64,
        )

    def test_explicit_artifact_and_image_use_complete_encoded_urls(self):
        version = {"name": "1.0.0", "hash": ARCHIVE_HASH, "artifact": ARTIFACT_URL}
        rewritten = self.rewrite(plugin_catalogue([version]))[0]
        self.assertEqual(
            rewritten["versions"][0]["artifact"],
            "https://mirror.example/resources/base64/" + encode_resource_url(ARTIFACT_URL),
        )
        self.assertEqual(
            rewritten["image_url"],
            "https://mirror.example/resources/base64/" + encode_resource_url(IMAGE_URL),
        )

    def test_rewriting_preserves_fields_hashes_order_and_original_input(self):
        original = plugin_catalogue(
            [
                {"name": "3.0.0", "hash": "c" * 64, "extra": 42},
                {"name": "1.0.0", "hash": ARCHIVE_HASH},
            ]
        )
        unchanged = copy.deepcopy(original)
        rewritten = self.rewrite(original)[0]
        self.assertEqual(original, unchanged)
        self.assertEqual(rewritten["unknown_field"], original[0]["unknown_field"])
        self.assertEqual(
            [version["hash"] for version in rewritten["versions"]],
            ["c" * 64, ARCHIVE_HASH],
        )
        self.assertEqual(rewritten["versions"][0]["extra"], 42)

    def test_url_round_trip_preserves_utf8_escapes_and_query(self):
        urls = [
            ARTIFACT_URL,
            "https://images.example/тест.png?value=%2f&value=a+b#fragment",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(str(decode_resource_url(encode_resource_url(url))), url)
                self.assertNotIn("=", encode_resource_url(url))

    def test_invalid_catalogue_content_is_rejected(self):
        invalid = [b"not json", b"{}", b"[null]", b'[{"versions":null}]']
        for content in invalid:
            with (
                self.subTest(content=content),
                self.assertRaises(InvalidCatalogueError),
            ):
                rewrite_catalogue(content, "mirror.example")

    def test_empty_artifacts_and_invalid_image_urls_are_rejected(self):
        for artifact in ("", "ftp://downloads.example/file", 123):
            with (
                self.subTest(artifact=artifact),
                self.assertRaises(InvalidCatalogueError),
            ):
                self.rewrite(
                    plugin_catalogue(
                        [{"name": "1", "hash": ARCHIVE_HASH, "artifact": artifact}]
                    )
                )
        catalogue = plugin_catalogue()
        catalogue[0]["image_url"] = ""
        with self.assertRaises(InvalidCatalogueError):
            self.rewrite(catalogue)

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
