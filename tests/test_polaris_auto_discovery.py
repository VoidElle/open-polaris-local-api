"""Tests for PolarisAutoDiscovery helpers (no network required)."""
import asyncio
import json
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from open_polaris_local_api.polaris_auto_discovery import (
    PolarisAutoDiscovery,
    _build_probe,
    _is_valid_polaris_response,
)


# ─── _build_probe ─────────────────────────────────────────────────────────────

class TestBuildProbe(unittest.TestCase):

    def test_returns_bytes(self):
        self.assertIsInstance(_build_probe("1234"), bytes)

    def test_valid_json(self):
        parsed = json.loads(_build_probe("9999").decode("utf-8"))
        self.assertIsInstance(parsed, dict)

    def test_contains_pin(self):
        parsed = json.loads(_build_probe("5678").decode("utf-8"))
        self.assertEqual(parsed["pin"], "5678")

    def test_contains_cmd(self):
        parsed = json.loads(_build_probe("0").decode("utf-8"))
        self.assertEqual(parsed["c"], "stato_r")


# ─── _is_valid_polaris_response ───────────────────────────────────────────────

class TestIsValidPolarisResponse(unittest.TestCase):

    @staticmethod
    def _valid() -> dict[str, Any]:
        return {"res": 1, "fw_ver": "1.0", "serial": "SN001", "name": "TestCU"}

    def test_valid_response_res1_accepted(self):
        self.assertTrue(_is_valid_polaris_response(self._valid()))

    def test_valid_response_res4_accepted(self):
        r = self._valid()
        r["res"] = 4  # old firmware: stato_r not found, still a Polaris device
        self.assertTrue(_is_valid_polaris_response(r))

    def test_non_dict_rejected(self):
        for inp in ["not a dict", None, [], 42]:
            self.assertFalse(_is_valid_polaris_response(inp))

    def test_missing_fw_ver_rejected(self):
        r = self._valid()
        del r["fw_ver"]
        self.assertFalse(_is_valid_polaris_response(r))

    def test_missing_serial_rejected(self):
        r = self._valid()
        del r["serial"]
        self.assertFalse(_is_valid_polaris_response(r))

    def test_wrong_res_rejected(self):
        r = self._valid()
        r["res"] = 2
        self.assertFalse(_is_valid_polaris_response(r))

    def test_missing_res_rejected(self):
        r = self._valid()
        del r["res"]
        self.assertFalse(_is_valid_polaris_response(r))


# ─── _subnet_scan validation ──────────────────────────────────────────────────

class TestSubnetScanValidation(unittest.IsolatedAsyncioTestCase):

    async def test_ipv6_subnet_raises_value_error(self):
        with self.assertRaises(ValueError):
            await PolarisAutoDiscovery._subnet_scan(
                probe=b"",
                subnet="fd00::/64",
                port=1235,
                probe_timeout=0.01,
                max_concurrent=1,
                verbose=False,
            )

    async def test_invalid_subnet_raises_value_error(self):
        with self.assertRaises(ValueError):
            await PolarisAutoDiscovery._subnet_scan(
                probe=b"",
                subnet="not_a_subnet",
                port=1235,
                probe_timeout=0.01,
                max_concurrent=1,
                verbose=False,
            )


# ─── _probe_host ──────────────────────────────────────────────────────────────

_VALID_RESPONSE = {"res": 1, "fw_ver": "1.0", "serial": "SN001", "name": "TestCU"}


def _make_tcp_mock(response: dict):
    """Return (reader, writer) mocks that simulate a single Polaris TCP response."""
    reader = AsyncMock()
    encoded = json.dumps(response).encode("utf-8")
    reader.read.side_effect = [encoded, b""]

    writer = AsyncMock()
    writer.wait_closed = AsyncMock(return_value=None)
    return reader, writer


class TestProbeHost(unittest.IsolatedAsyncioTestCase):

    async def test_valid_response_returns_ip(self):
        reader, writer = _make_tcp_mock(_VALID_RESPONSE)
        with patch("asyncio.open_connection", return_value=(reader, writer)):
            result = await PolarisAutoDiscovery._probe_host("192.168.1.1", 1235, b"probe", 1.5, False)
        self.assertEqual(result, "192.168.1.1")

    async def test_valid_response_res4_returns_ip(self):
        reader, writer = _make_tcp_mock({**_VALID_RESPONSE, "res": 4})
        with patch("asyncio.open_connection", return_value=(reader, writer)):
            result = await PolarisAutoDiscovery._probe_host("192.168.1.2", 1235, b"probe", 1.5, False)
        self.assertEqual(result, "192.168.1.2")

    async def test_invalid_response_returns_none(self):
        reader, writer = _make_tcp_mock({"res": 0, "something": "else"})
        with patch("asyncio.open_connection", return_value=(reader, writer)):
            result = await PolarisAutoDiscovery._probe_host("192.168.1.3", 1235, b"probe", 1.5, False)
        self.assertIsNone(result)

    async def test_connection_refused_returns_none(self):
        with patch("asyncio.open_connection", side_effect=OSError("refused")):
            result = await PolarisAutoDiscovery._probe_host("192.168.1.4", 1235, b"probe", 1.5, False)
        self.assertIsNone(result)

    async def test_timeout_returns_none(self):
        with patch("asyncio.open_connection", side_effect=asyncio.TimeoutError):
            result = await PolarisAutoDiscovery._probe_host("192.168.1.5", 1235, b"probe", 1.5, False)
        self.assertIsNone(result)

    async def test_empty_response_returns_none(self):
        reader = AsyncMock()
        reader.read.side_effect = [b""]
        writer = AsyncMock()
        writer.wait_closed = AsyncMock(return_value=None)
        with patch("asyncio.open_connection", return_value=(reader, writer)):
            result = await PolarisAutoDiscovery._probe_host("192.168.1.6", 1235, b"probe", 1.5, False)
        self.assertIsNone(result)

    async def test_invalid_json_returns_none(self):
        reader = AsyncMock()
        reader.read.side_effect = [b"not json", b""]
        writer = AsyncMock()
        writer.wait_closed = AsyncMock(return_value=None)
        with patch("asyncio.open_connection", return_value=(reader, writer)):
            result = await PolarisAutoDiscovery._probe_host("192.168.1.7", 1235, b"probe", 1.5, False)
        self.assertIsNone(result)


# ─── discover (integration-style, mocked) ────────────────────────────────────

class TestDiscover(unittest.IsolatedAsyncioTestCase):

    async def test_returns_sorted_discovered_ips(self):
        """Only hosts with valid Polaris responses appear in the result."""
        valid = json.dumps(_VALID_RESPONSE).encode()

        async def fake_open_connection(ip, port):
            reader = AsyncMock()
            writer = AsyncMock()
            writer.wait_closed = AsyncMock(return_value=None)
            if ip in ("192.168.1.10", "192.168.1.20"):
                reader.read.side_effect = [valid, b""]
            else:
                raise OSError("no device")
            return reader, writer

        with patch("asyncio.open_connection", side_effect=fake_open_connection):
            result = await PolarisAutoDiscovery.discover(
                pin="1234",
                subnet="192.168.1.0/24",
                probe_timeout=0.1,
            )

        self.assertIn("192.168.1.10", result)
        self.assertIn("192.168.1.20", result)
        self.assertEqual(result, sorted(result))

    async def test_no_devices_returns_empty_list(self):
        with patch("asyncio.open_connection", side_effect=OSError("no device")):
            result = await PolarisAutoDiscovery.discover(
                pin="1234",
                subnet="192.168.1.0/24",
                probe_timeout=0.1,
            )
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
