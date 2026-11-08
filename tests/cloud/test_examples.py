"""Smoke tests: run the cloud examples against the fake backend (no real cloud)."""
import contextlib
import functools
import importlib.util
import io
import json
import os
import sys
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestServer

from open_polaris_local_api.cloud import PolarisCloudClient
from tests.cloud.test_cloud_client import ANDROID_ID, make_backend

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "..", "examples", "cloud")
CREDS = ["--email", "a@b.c", "--password", "secret"]
DEVICE = CREDS + ["--serial", "cu1", "--pin", "1234"]


def load(name: str):
    if EXAMPLES not in sys.path:
        sys.path.insert(0, EXAMPLES)  # examples import their sibling _common
    spec = importlib.util.spec_from_file_location(f"cloud_example_{name}", os.path.join(EXAMPLES, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CloudExamplesTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sent, self.state, self.counter = [], {}, {}
        self.server = TestServer(make_backend(self.sent, self.state, self.counter))
        await self.server.start_server()

    async def asyncTearDown(self):
        await self.server.close()

    async def run_example(self, name: str, *argv: str) -> str:
        module = load(name)
        # Examples build the client with the default backend: point it at the fake one.
        module.PolarisCloudClient = functools.partial(
            PolarisCloudClient, base_url=str(self.server.make_url("")), android_id=ANDROID_ID, retry_delay=0)
        out = io.StringIO()
        with patch.object(sys, "argv", [name, *argv]), contextlib.redirect_stdout(out):
            await module.main()
        return out.getvalue()

    async def test_login(self):
        out = await self.run_example("login", *CREDS)
        self.assertIn("Login OK.", out)
        self.assertIn("Devices: 2 (all types)", out)

    async def test_list_devices(self):
        out = await self.run_example("list_devices", *CREDS)
        self.assertIn("CU1", out)
        self.assertIn("CU2", out)
        self.assertNotIn("PICO1", out)  # Polaris CUs only
        raw = json.loads(await self.run_example("list_devices", *CREDS, "--json"))
        self.assertEqual(len(raw[0]["ListDevices"]), 3)  # raw plants keep every device type

    async def test_basic_cloud(self):
        out = await self.run_example("basic_cloud", *DEVICE)
        self.assertIn("CU 'CASA' (CU1", out)
        self.assertIn("Heating mode queued.", out)
        self.assertEqual(self.sent[0][0], "/api/v1/UpdateCUData")

    async def test_simple_actions(self):
        out = await self.run_example("simple_actions", *DEVICE, "status")
        self.assertIn("zone 1 'Living'", out)
        self.assertEqual(self.sent, [])
        await self.run_example("simple_actions", *DEVICE, "zone-temp", "22.5", "--zone", "1")
        path, body = self.sent[0]
        self.assertEqual((path, json.loads(body["Cmd"])["t_set"]), ("/api/v1/UpdateZonaData", "225"))

    async def test_multi_device_cloud(self):
        out = await self.run_example("multi_device_cloud", *CREDS, "--pins", "cu1=1234", "--turn", "on", "--heat")
        self.assertIn("2 Polaris CU(s)", out)
        self.assertIn("HOME/Ufficio: skipped (no PIN)", out)
        self.assertIn("(changes queued)", out)
        self.assertEqual([(p, b["Serial"]) for p, b in self.sent],
                         [("/api/v1/UpdateCUData", "CU1"), ("/api/v1/UpdateCUData", "CU1")])


if __name__ == "__main__":
    unittest.main()
