import socket
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp.resolver import ThreadedResolver
from yarl import URL

from errors import BlockedDestinationError, InvalidResourceError
from security import (
    BlockedAddressLookupError,
    PublicAddressResolver,
    parse_url,
    validate_destination,
)


class DestinationTests(unittest.TestCase):
    def test_non_public_ipv4_and_ipv6_are_blocked(self):
        hosts = [
            "127.0.0.1",
            "127.255.0.1",
            "10.0.0.1",
            "172.16.0.1",
            "192.168.1.1",
            "169.254.169.254",
            "100.64.0.1",
            "0.0.0.0",
            "224.0.0.1",
            "240.0.0.1",
            "[::1]",
            "[::]",
            "[fc00::1]",
            "[fe80::1]",
            "[ff02::1]",
            "[::ffff:127.0.0.1]",
        ]
        for host in hosts:
            with self.subTest(host=host), self.assertRaises(BlockedDestinationError):
                validate_destination(parse_url("http://" + host + "/"))

    def test_localhost_names_are_blocked_without_dns(self):
        for host in ("localhost", "LOCALHOST.", "sub.localhost"):
            with self.subTest(host=host), self.assertRaises(BlockedDestinationError):
                validate_destination(parse_url("http://" + host + "/"))

    def test_public_literals_are_allowed(self):
        for host in ("1.1.1.1", "8.8.8.8", "[2606:4700:4700::1111]"):
            with self.subTest(host=host):
                validate_destination(parse_url("https://" + host + "/"))

    def test_numeric_shorthand_cannot_bypass_dns_validation(self):
        for host in ("127.1", "2130706433", "0177.0.0.1"):
            with self.subTest(host=host), self.assertRaises(InvalidResourceError):
                validate_destination(URL("http://" + host + "/"))


class ResolverTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.resolver = PublicAddressResolver()

    async def asyncTearDown(self):
        await self.resolver.close()

    async def test_private_dns_results_are_blocked(self):
        with (
            patch.object(
                ThreadedResolver,
                "resolve",
                AsyncMock(return_value=[{"host": "127.0.0.1"}]),
            ),
            self.assertRaises(BlockedAddressLookupError),
        ):
            await self.resolver.resolve("local.example")

    async def test_mixed_dns_results_are_blocked(self):
        addresses = [{"host": "1.1.1.1"}, {"host": "10.0.0.1"}]
        with (
            patch.object(
                ThreadedResolver, "resolve", AsyncMock(return_value=addresses)
            ),
            self.assertRaises(BlockedAddressLookupError),
        ):
            await self.resolver.resolve("mixed.example")

    async def test_public_numeric_results_are_returned_without_another_lookup(self):
        addresses = [
            {
                "hostname": "public.example",
                "host": "1.1.1.1",
                "port": 443,
                "family": socket.AF_INET,
                "proto": 0,
                "flags": socket.AI_NUMERICHOST,
            }
        ]
        lookup = AsyncMock(return_value=addresses)
        with patch.object(ThreadedResolver, "resolve", lookup):
            self.assertIs(await self.resolver.resolve("public.example", 443), addresses)
        lookup.assert_awaited_once_with("public.example", 443, socket.AF_INET)

    async def test_empty_dns_results_are_a_lookup_failure(self):
        with (
            patch.object(ThreadedResolver, "resolve", AsyncMock(return_value=[])),
            self.assertRaises(OSError),
        ):
            await self.resolver.resolve("unknown.example")
