"""Offline tests: fake backend that enforces the rolling-token counter."""
import json
import unittest

from aiohttp import web
from aiohttp.test_utils import TestServer

from open_polaris_local_api import PolarisApiError
from open_polaris_local_api.cloud import PolarisAuthError, PolarisCloudClient
from open_polaris_local_api.cloud.crypto import PolarisCipher

ANDROID_ID = "0123456789abcdef"
# GetCUState shape (docs/app/http-flows/04-polaris-cloud-runtime.md): flat PascalCase, no ResCode.
STATE = {"Serial": "CU1", "Name": "CASA", "FWVer": "5.1", "IP": "192.168.1.50", "IsOFF": False,
         "IsCooling": True, "OperatingModeCooling": 2, "TempCan": 180, "FInv": 1, "FEst": 0,
         "IrPresent": 0, "Errors": 32,
         "Zones": [{"ZoneId": 1, "Name": "Living", "Temp": "215", "SetTemp": "95", "IsOFF": False,
                    "Fancoil": -1, "FancoilSet": -1, "Serranda": 0, "SerrandaSet": 2, "EV": 1,
                    "Umd": "45", "SetUmd": "50", "IsCronoMode": True, "IsMaster": True, "Errors": 16}]}


def make_backend(sent: list, state: dict, counter: dict) -> web.Application:
    cipher = PolarisCipher(ANDROID_ID)
    counter.update(n=1, logins=0)

    async def login(req):
        body = await req.json()
        assert req.headers["Token"] == "Ga5mM61KCm5Bk18lhD5J999jC2Mu0Vaf"
        if cipher.decrypt(body["Password"]) != "secret":
            return web.json_response({"ResCode": 1})
        counter["n"], counter["logins"] = 1, counter["logins"] + 1
        plants = [{"LVPL_Id": 1, "LVPL_Name": "HOME", "ListDevices": [
            {"Serial": "CU1", "Name": "Casa", "LVDV_Type": 0},
            {"Serial": "PICO1", "Name": "Vmc", "LVDV_Type": 1}]}]
        return web.json_response({"ResCode": 0, "ID": 7, "ListPlants": json.dumps(plants),
                                  "Token": cipher.encrypt("sess_1").replace("\n", "")})

    def token_ok(req):
        _, _, n = cipher.decrypt(req.headers["Token"]).rpartition("_")
        counter["n"] += 1
        return int(n) == counter["n"] and not state.get("expire")

    async def get_state(req):
        if not token_ok(req):
            state.pop("expire", None)
            return web.Response(status=401)
        if req.query["PIN"] != "1234":
            return web.json_response({"ResCode": 2}, status=400)
        return web.json_response(json.loads(json.dumps(STATE)))

    async def update(req):
        if not token_ok(req):
            return web.Response(status=401)
        sent.append((req.path, await req.json()))
        return web.json_response({"ResCode": 0, "ResDescr": ""})

    async def plants(req):
        if not token_ok(req):
            return web.Response(status=401)
        return web.json_response({"ResCode": 0, "ResDescr": json.dumps([
            {"LVPL_Id": 1, "LVPL_Name": "HOME", "ListDevices": [
                {"Serial": "CU1", "Name": "Casa", "LVDV_Type": 0},
                {"Serial": "CU2", "Name": "Ufficio", "LVDV_Type": 0},
                {"Serial": "PICO1", "Name": "Vmc", "LVDV_Type": 1}]}])})

    app = web.Application()
    app.router.add_post("/apiTS/v2/Login", login)
    app.router.add_get("/api/v1/GetCUState", get_state)
    app.router.add_get("/api/v1/GetPlants", plants)
    app.router.add_post("/api/v1/UpdateCUData", update)
    app.router.add_post("/api/v1/UpdateZonaData", update)
    return app


class CloudClientTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sent, self.state, self.counter = [], {}, {}
        self.server = TestServer(make_backend(self.sent, self.state, self.counter))
        await self.server.start_server()

    async def asyncTearDown(self):
        await self.server.close()

    def client(self, password="secret", serial="cu1", pin="1234"):
        return PolarisCloudClient("a@b.c", password, serial, pin, android_id=ANDROID_ID,
                                  base_url=str(self.server.make_url("")), retry_delay=0)

    async def test_connect_parses_state(self):
        async with self.client() as c:
            dev, zones = c.device, c.zones
        self.assertEqual((dev.serial, dev.ip, dev.operating_mode, dev.t_can), ("CU1", "192.168.1.50", 2, 18))
        self.assertEqual(dev.num_errors, 32)  # cloud CU "Errors" bitmask
        z = zones[0]
        self.assertEqual((z.current_temp, z.set_temp), (21.5, 9.5))  # tenths, also below 10 °C
        self.assertTrue(z.is_master and z.is_crono_mode)
        self.assertEqual((z.serranda, z.serranda_set, z.num_error), (0, 2, 16))

    async def test_writes_use_cloud_envelopes(self):
        async with self.client() as c:
            await c.turn_off()
            await c.set_zone_temp(c.zones[0], 20.0)
            self.assertEqual(await c.fetch_all_zone_details(), {})
        (cu_path, cu), (z_path, zone) = self.sent
        self.assertEqual((cu_path, cu["Serial"], cu["Name"], cu["Pin"]), ("/api/v1/UpdateCUData", "CU1", "CASA", "1234"))
        self.assertEqual(json.loads(cu["Cmd"]), {"c": "upd_cu", "pin": "1234", "is_off": 1, "is_cool": 1,
                                                 "cool_mod": 2, "t_can": 180, "f_inv": 1, "f_est": 0})
        self.assertEqual((z_path, zone["ZoneId"]), ("/api/v1/UpdateZonaData", 1))
        inner = json.loads(zone["Cmd"])
        self.assertEqual((inner["c"], inner["id_zona"], inner["t_set"], inner["shu_set"], inner["fan_set"]),
                         ("upd_zona", 1, "200", 2, 2))

    async def test_relogin_on_401(self):
        async with self.client() as c:
            self.state["expire"] = True
            await c.async_update()
        self.assertEqual(self.counter["logins"], 2)

    async def test_relogin_on_bad_token(self):
        async with self.client() as c:
            c._token = "garbage"
            await c.async_update()
        self.assertEqual(self.counter["logins"], 2)

    async def test_login_only_list_and_switch(self):
        async with self.client(serial="") as c:
            self.assertIsNone(c.device)
            devices = await c.get_devices()
            self.assertEqual([(d["Serial"], d["PlantName"]) for d in devices], [("CU1", "HOME"), ("CU2", "HOME")])
            c.use_device("cu1", "1234")
            with self.assertRaises(PolarisApiError):
                await c.turn_on()  # no cached state: must not queue a zero-filled upd_cu
            await c.async_update()
            self.assertEqual(c.device.name, "CASA")

    async def test_bad_password(self):
        with self.assertRaises(PolarisAuthError):
            await self.client(password="nope").connect()

    async def test_wrong_pin(self):
        c = self.client(pin="0000")
        with self.assertRaises(PolarisApiError):
            await c.connect()
        self.assertFalse(c.connected)

    async def test_backend_unreachable(self):
        c = PolarisCloudClient("a@b.c", "secret", "cu1", "1234", base_url="http://127.0.0.1:9",
                               retry_delay=0, timeout=2)
        with self.assertRaises(TimeoutError):
            await c.connect()


class CryptoTest(unittest.TestCase):
    def test_roundtrip_and_token(self):
        c = PolarisCipher(ANDROID_ID)
        self.assertEqual(c.decrypt(c.encrypt("hello")), "hello")
        self.assertEqual(c.decrypt(c.next_token(c.encrypt("x_y_5"))), "x_y_6")


if __name__ == "__main__":
    unittest.main()
