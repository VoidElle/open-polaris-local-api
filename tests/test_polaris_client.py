"""Tests for polaris_client.py — PolarisLocalClient protocol behaviour."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from open_polaris_local_api import PolarisApiError, PolarisLocalClient
from open_polaris_local_api import PolarisDevice, PolarisZone


# ─── Helpers ──────────────────────────────────────────────────────────────────

_STATUS_RIDOTTO = {
    "res": 1,
    "off": 0,
    "cl": 1,
    "cl_m": 1,
    "tc": 220,
    "fi": 2,
    "fe": 1,
    "ir": 0,
    "err_cu": 0,
    "serial": "SN001",
    "name": "TestCU",
    "fw_ver": "1.0",
    "ip": "192.168.1.100",
    "zone": [
        {
            "id_zona": 1,
            "n": "Zone A",
            "co": 210,
            "ts": 220,
            "off": 0,
            "cl": 1,
            "fan": 2,
            "fan_set": 2,
            "shu": -1,
            "shu_set": -1,
            "EV": 0,
            "err": 0,
        }
    ],
}


def _make_tcp_mock(response: dict):
    """Return (reader, writer) mocks that return a single JSON response."""
    reader = AsyncMock()
    encoded = json.dumps(response).encode("utf-8")
    reader.read.side_effect = [encoded, b""]
    writer = MagicMock()
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    return reader, writer


def _patch_tcp(response: dict):
    reader, writer = _make_tcp_mock(response)
    return patch(
        "asyncio.open_connection",
        new=AsyncMock(return_value=(reader, writer)),
    )


# ─── Init / properties ────────────────────────────────────────────────────────

class TestPolarisLocalClientInit(unittest.TestCase):

    def test_defaults(self):
        client = PolarisLocalClient("192.168.1.1", "1234")
        self.assertEqual(client.ip, "192.168.1.1")
        self.assertEqual(client.pin, "1234")
        self.assertEqual(client.port, 1235)
        self.assertEqual(client.timeout, 5.0)
        self.assertEqual(client.retry_attempts, 2)
        self.assertFalse(client.connected)
        self.assertIsNone(client.device)
        self.assertEqual(client.zones, [])

    def test_auto_device_id(self):
        client = PolarisLocalClient("10.0.0.1", "0000")
        self.assertIn("10.0.0.1", client.device_id)

    def test_custom_device_id(self):
        client = PolarisLocalClient("10.0.0.1", "0000", device_id="my_unit")
        self.assertEqual(client.device_id, "my_unit")

    def test_custom_port(self):
        client = PolarisLocalClient("10.0.0.1", "0000", port=9999)
        self.assertEqual(client.port, 9999)


# ─── Connect / disconnect ─────────────────────────────────────────────────────

class TestPolarisLocalClientConnection(unittest.IsolatedAsyncioTestCase):

    async def test_connect_sets_connected(self):
        client = PolarisLocalClient("192.168.1.1", "1234")
        with _patch_tcp(_STATUS_RIDOTTO):
            await client.connect()
        self.assertTrue(client.connected)

    async def test_connect_idempotent(self):
        client = PolarisLocalClient("192.168.1.1", "1234")
        with _patch_tcp(_STATUS_RIDOTTO):
            await client.connect()
            await client.connect()  # second call is a no-op
        self.assertTrue(client.connected)

    async def test_disconnect_clears_connected(self):
        client = PolarisLocalClient("192.168.1.1", "1234")
        with _patch_tcp(_STATUS_RIDOTTO):
            await client.connect()
        await client.disconnect()
        self.assertFalse(client.connected)

    async def test_close_alias(self):
        client = PolarisLocalClient("192.168.1.1", "1234")
        with _patch_tcp(_STATUS_RIDOTTO):
            await client.connect()
        await client.close()
        self.assertFalse(client.connected)

    async def test_context_manager(self):
        client = PolarisLocalClient("192.168.1.1", "1234")
        with _patch_tcp(_STATUS_RIDOTTO):
            async with client as c:
                self.assertTrue(c.connected)
        self.assertFalse(client.connected)


# ─── get_status (stato_r / fallback) ─────────────────────────────────────────

class TestGetStatus(unittest.IsolatedAsyncioTestCase):

    async def test_stato_r_success(self):
        client = PolarisLocalClient("192.168.1.1", "1234")
        with _patch_tcp(_STATUS_RIDOTTO):
            result = await client.get_status()
        self.assertEqual(result["res"], 1)

    async def test_stato_r_fallback_on_res4(self):
        """If stato_r returns res=4, client must retry with stato."""
        res4 = {"res": 4}
        full_status = dict(_STATUS_RIDOTTO)

        call_count = 0
        reader1, writer1 = _make_tcp_mock(res4)
        reader2, writer2 = _make_tcp_mock(full_status)

        async def fake_open_connection(_host, _port, **_kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return reader1, writer1
            return reader2, writer2

        client = PolarisLocalClient("192.168.1.1", "1234", retry_attempts=1)
        with patch("asyncio.open_connection", side_effect=fake_open_connection):
            result = await client.get_status()

        self.assertEqual(result["serial"], "SN001")
        self.assertEqual(call_count, 2)

    async def test_no_response_raises_timeout(self):
        client = PolarisLocalClient("192.168.1.1", "1234", retry_attempts=1)
        reader = AsyncMock()
        reader.read.return_value = b""
        writer = MagicMock()
        writer.drain = AsyncMock()
        writer.wait_closed = AsyncMock()
        with patch("asyncio.open_connection", return_value=(reader, writer)):
            with self.assertRaises(TimeoutError):
                await client.get_status()


# ─── async_update ─────────────────────────────────────────────────────────────

class TestAsyncUpdate(unittest.IsolatedAsyncioTestCase):

    async def test_update_populates_device_and_zones(self):
        client = PolarisLocalClient("192.168.1.1", "1234")
        with _patch_tcp(_STATUS_RIDOTTO):
            device, zones = await client.async_update()

        self.assertIsInstance(device, PolarisDevice)
        self.assertEqual(device.name, "TestCU")
        self.assertTrue(client.connected)
        self.assertEqual(len(zones), 1)
        self.assertEqual(zones[0].name, "Zone A")

    async def test_zones_empty_when_missing(self):
        status = dict(_STATUS_RIDOTTO)
        status.pop("zone")
        client = PolarisLocalClient("192.168.1.1", "1234")
        with _patch_tcp(status):
            _, zones = await client.async_update()
        self.assertEqual(zones, [])

    async def test_zones_skips_non_dict(self):
        status = dict(_STATUS_RIDOTTO)
        status["zone"] = [{"id_zona": 1, "n": "Z1"}, "bad", None]
        client = PolarisLocalClient("192.168.1.1", "1234")
        with _patch_tcp(status):
            _, zones = await client.async_update()
        self.assertEqual(len(zones), 1)


# ─── update_zone ──────────────────────────────────────────────────────────────

class TestUpdateZone(unittest.IsolatedAsyncioTestCase):

    @staticmethod
    def _make_client():
        client = PolarisLocalClient("192.168.1.1", "1234")
        zone = PolarisZone(
            zone_id=1, name="Zone A",
            set_temp=21.0, is_off=False, is_cooling=True,
            fancoil=2, fancoil_set=2, serranda=-1, serranda_set=-1,
        )
        return client, zone

    async def test_sends_upd_zona(self):
        client, zone = self._make_client()
        sent_cmd = {}

        async def fake_send(cmd):
            sent_cmd.update(cmd)
            return {"res": 1}

        client._send_command_with_retry = fake_send
        await client.update_zone(zone, set_temp=22.0, is_off=False)

        self.assertEqual(sent_cmd["c"], "upd_zona")
        self.assertEqual(sent_cmd["id_zona"], 1)
        self.assertEqual(sent_cmd["t_set"], "220")  # stored as str(int*10)
        self.assertEqual(sent_cmd["is_off"], 0)
        self.assertEqual(sent_cmd["pin"], "1234")

    async def test_fan_sentinel_7_maps_to_16(self):
        client, zone = self._make_client()
        zone.fancoil_set = 7
        sent_cmd = {}

        async def fake_send(cmd):
            sent_cmd.update(cmd)
            return {"res": 1}

        client._send_command_with_retry = fake_send
        await client.update_zone(zone)

        self.assertEqual(sent_cmd["fan_set"], 16)
        self.assertEqual(sent_cmd["shu_set"], 16)

    async def test_raises_when_no_temp(self):
        client, zone = self._make_client()
        zone.set_temp = None
        with self.assertRaises(ValueError):
            await client.update_zone(zone)

    async def test_serranda_only_zone(self):
        client, zone = self._make_client()
        zone.fancoil = -1
        zone.serranda = 2
        zone.serranda_set = 3
        sent_cmd = {}

        async def fake_send(cmd):
            sent_cmd.update(cmd)
            return {"res": 1}

        client._send_command_with_retry = fake_send
        await client.update_zone(zone)

        self.assertEqual(sent_cmd["shu_set"], 3)
        self.assertEqual(sent_cmd["fan_set"], 3)


# ─── update_cu ────────────────────────────────────────────────────────────────

class TestUpdateCu(unittest.IsolatedAsyncioTestCase):

    @staticmethod
    async def _setup_with_device():
        client = PolarisLocalClient("192.168.1.1", "1234")
        with _patch_tcp(_STATUS_RIDOTTO):
            await client.async_update()
        return client

    async def test_sends_upd_cu(self):
        client = await self._setup_with_device()
        sent_cmd = {}

        async def fake_send(cmd):
            sent_cmd.update(cmd)
            return {"res": 1}

        client._send_command_with_retry = fake_send
        await client.update_cu(is_off=True, is_cooling=False)

        self.assertEqual(sent_cmd["c"], "upd_cu")
        self.assertEqual(sent_cmd["is_off"], 1)
        self.assertEqual(sent_cmd["is_cool"], 0)
        self.assertEqual(sent_cmd["pin"], "1234")

    async def test_uses_cached_device_values(self):
        client = await self._setup_with_device()
        sent_cmd = {}

        async def fake_send(cmd):
            sent_cmd.update(cmd)
            return {"res": 1}

        client._send_command_with_retry = fake_send
        await client.update_cu()

        # is_off and is_cool from cached device
        self.assertEqual(sent_cmd["is_off"], 0)
        self.assertEqual(sent_cmd["is_cool"], 1)

    async def test_no_device_uses_defaults(self):
        client = PolarisLocalClient("192.168.1.1", "1234")
        sent_cmd = {}

        async def fake_send(cmd):
            sent_cmd.update(cmd)
            return {"res": 1}

        client._send_command_with_retry = fake_send
        await client.update_cu()

        self.assertEqual(sent_cmd["is_off"], 0)
        self.assertEqual(sent_cmd["t_can"], 0)


# ─── Convenience methods ──────────────────────────────────────────────────────

class TestConvenienceMethods(unittest.IsolatedAsyncioTestCase):

    @staticmethod
    async def _client_with_zone():
        client = PolarisLocalClient("192.168.1.1", "1234")
        with _patch_tcp(_STATUS_RIDOTTO):
            await client.async_update()
        return client, client.zones[0]

    async def test_turn_on(self):
        client, _ = await self._client_with_zone()
        cmds = []
        async def fake_send(cmd):
            cmds.append(cmd)
            return {"res": 1}
        client._send_command_with_retry = fake_send
        await client.turn_on()
        self.assertEqual(cmds[-1]["is_off"], 0)

    async def test_turn_off(self):
        client, _ = await self._client_with_zone()
        cmds = []
        async def fake_send(cmd):
            cmds.append(cmd)
            return {"res": 1}
        client._send_command_with_retry = fake_send
        await client.turn_off()
        self.assertEqual(cmds[-1]["is_off"], 1)

    async def test_set_heating_mode(self):
        client, _ = await self._client_with_zone()
        cmds = []
        async def fake_send(cmd):
            cmds.append(cmd)
            return {"res": 1}
        client._send_command_with_retry = fake_send
        await client.set_heating_mode()
        self.assertEqual(cmds[-1]["is_cool"], 0)
        self.assertEqual(cmds[-1]["cool_mod"], 0)

    async def test_set_cooling_mode(self):
        client, _ = await self._client_with_zone()
        cmds = []
        async def fake_send(cmd):
            cmds.append(cmd)
            return {"res": 1}
        client._send_command_with_retry = fake_send
        await client.set_cooling_mode(2)
        self.assertEqual(cmds[-1]["is_cool"], 1)
        self.assertEqual(cmds[-1]["cool_mod"], 2)

    async def test_set_zone_temp(self):
        client, zone = await self._client_with_zone()
        cmds = []
        async def fake_send(cmd):
            cmds.append(cmd)
            return {"res": 1}
        client._send_command_with_retry = fake_send
        await client.set_zone_temp(zone, 24.0)
        self.assertEqual(cmds[-1]["t_set"], "240")  # stored as str(int*10)

    async def test_turn_zone_on(self):
        client, zone = await self._client_with_zone()
        cmds = []
        async def fake_send(cmd):
            cmds.append(cmd)
            return {"res": 1}
        client._send_command_with_retry = fake_send
        await client.turn_zone_on(zone)
        self.assertEqual(cmds[-1]["is_off"], 0)

    async def test_turn_zone_off(self):
        client, zone = await self._client_with_zone()
        cmds = []
        async def fake_send(cmd):
            cmds.append(cmd)
            return {"res": 1}
        client._send_command_with_retry = fake_send
        await client.turn_zone_off(zone)
        self.assertEqual(cmds[-1]["is_off"], 1)


# ─── Retry / transport ────────────────────────────────────────────────────────

class TestRetryLogic(unittest.IsolatedAsyncioTestCase):

    async def test_retries_on_timeout(self):
        client = PolarisLocalClient("192.168.1.1", "1234", retry_attempts=3, retry_delay=0)
        attempt = 0

        async def fake_open(_host, _port, **_kw):
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise asyncio.TimeoutError()
            return _make_tcp_mock(_STATUS_RIDOTTO)

        with patch("asyncio.open_connection", side_effect=fake_open):
            result = await client._send_command_with_retry({"c": "stato_r", "pin": "1234"})

        self.assertIsNotNone(result)
        self.assertEqual(attempt, 3)

    async def test_returns_none_after_all_retries_fail(self):
        client = PolarisLocalClient("192.168.1.1", "1234", retry_attempts=2, retry_delay=0)

        reader = AsyncMock()
        reader.read.return_value = b""
        writer = MagicMock()
        writer.drain = AsyncMock()
        writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", return_value=(reader, writer)):
            result = await client._send_command_with_retry({"c": "stato_r", "pin": "1234"})

        self.assertIsNone(result)

    async def test_oserror_caught_and_retried(self):
        client = PolarisLocalClient("192.168.1.1", "1234", retry_attempts=2, retry_delay=0)
        call = 0

        async def fake_open(_host, _port, **_kw):
            nonlocal call
            call += 1
            if call == 1:
                raise OSError("connection refused")
            return _make_tcp_mock(_STATUS_RIDOTTO)

        with patch("asyncio.open_connection", side_effect=fake_open):
            result = await client._send_command_with_retry({"c": "stato_r", "pin": "1234"})

        self.assertIsNotNone(result)


# ─── PolarisApiError ──────────────────────────────────────────────────────────

class TestPolarisApiError(unittest.TestCase):

    def test_is_exception(self):
        err = PolarisApiError("something went wrong")
        self.assertIsInstance(err, Exception)
        self.assertIn("something went wrong", str(err))


if __name__ == "__main__":
    unittest.main()
