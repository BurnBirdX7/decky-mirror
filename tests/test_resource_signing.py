import hmac
import os
import subprocess
import sys
import unittest
from base64 import urlsafe_b64encode
from pathlib import Path
from unittest.mock import patch

from tests.support import IMAGE_URL, TEST_ENVIRONMENT

with patch.dict(os.environ, TEST_ENVIRONMENT):
    from decky_mirror import resource_signing
    from decky_mirror.catalogue import encode_resource_url

from decky_mirror.errors import InvalidResourceSignatureError


class ResourceSigningTests(unittest.TestCase):
    def test_signature_matches_truncated_hmac_and_preserves_padding(self):
        token = encode_resource_url("https://example.com/")
        key = b"known-test-key"
        expected = urlsafe_b64encode(hmac.digest(key, token.encode("ascii"), "sha256")[:16]).decode().rstrip("=")
        with patch.object(resource_signing, "_SIGNING_KEY", key):
            signed = resource_signing.sign_resource_token(token)
            self.assertEqual(signed, token + "." + expected)
            self.assertEqual(len(signed) - len(token), 23)
            self.assertEqual(resource_signing.unsign_resource_token(signed), token)
            self.assertEqual(resource_signing.sign_resource_token(token), signed)

    def test_different_key_rejects_previously_signed_token(self):
        token = encode_resource_url(IMAGE_URL)
        with patch.object(resource_signing, "_SIGNING_KEY", b"first-key"):
            signed = resource_signing.sign_resource_token(token)
        with (
            patch.object(resource_signing, "_SIGNING_KEY", b"second-key"),
            self.assertRaisesRegex(InvalidResourceSignatureError, "Invalid resource signature"),
        ):
            resource_signing.unsign_resource_token(signed)

    def run_initialization(self, setting, assertions=""):
        environment = os.environ | TEST_ENVIRONMENT
        environment["PYTHONUTF8"] = "1"
        if setting is None:
            environment.pop("RESOURCE_SIGNING_KEY", None)
        else:
            environment["RESOURCE_SIGNING_KEY"] = setting
        code = (
            "from unittest.mock import patch\n"
            "with patch('dotenv.load_dotenv'), patch('secrets.token_bytes', return_value=b'x' * 32) as generate:\n"
            "    from decky_mirror import resource_signing as signing\n"
            + assertions
        )
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).resolve().parent.parent,
            env=environment,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            timeout=15,
        )

    def test_missing_and_empty_keys_prevent_startup(self):
        for setting in (None, ""):
            with self.subTest(setting=setting):
                result = self.run_initialization(setting)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("RESOURCE_SIGNING_KEY must be set", result.stderr)

    def test_random_key_is_generated_once_and_reused(self):
        result = self.run_initialization(
            "random",
            "    first = signing.sign_resource_token('AAAA')\n"
            "    assert signing.sign_resource_token('AAAA') == first\n"
            "    assert signing.unsign_resource_token(first) == 'AAAA'\n"
            "    generate.assert_called_once_with(32)\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_persistent_key_is_used_verbatim_as_utf8(self):
        for setting in ("  секрет  ", "RANDOM", " "):
            with self.subTest(setting=setting):
                result = self.run_initialization(
                    setting,
                    "    import os\n"
                    "    assert signing._SIGNING_KEY == os.environ['RESOURCE_SIGNING_KEY'].encode('utf-8')\n"
                    "    generate.assert_not_called()\n",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
