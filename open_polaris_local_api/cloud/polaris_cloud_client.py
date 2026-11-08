"""PolarisLocalClient drop-in that talks to the Tecnosystemi cloud instead of local TCP.

Writes (update_cu, update_zone and the convenience methods built on them) are inherited from
PolarisLocalClient: they only build the local command dict and call `_send_command_with_retry`,
which is replaced here by an `UpdateCUData` / `UpdateZonaData` REST call carrying the same
command double-encoded in `Cmd`. Reads go to `GetCUState`. See docs/app/http-flows/.

This is a separate fallback flow: it never touches the LAN and the local client never calls it.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from typing import Any, Optional

import aiohttp

from ..client import PolarisApiError, PolarisLocalClient

from .crypto import PolarisCipher
from .exceptions import PolarisAuthError

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://proair.azurewebsites.net"
FIX_TOKEN = "Ga5mM61KCm5Bk18lhD5J999jC2Mu0Vaf"  # token for unauthenticated calls
BASIC_PWD = "PwdProAir"
SESSION_TTL = 55 * 60  # server session lasts 1 h from login, no refresh endpoint
DEVICE_TYPE_POLARIS = 0  # LVDV_Type of a Polaris CU (PICO = 1)

_LOGIN_PATH = "/apiTS/v2/Login"
_LOGIN_ERRORS = {
    1: "wrong user or password",
    2: "user must confirm the email first",
    3: "user blocked",
    4: "user not found",
    6: "temporary password: change it in the official app",
    7: "request a new temporary password",
    10: "terms of use / privacy not accepted: accept them in the official app",
}


class PolarisCloudClient(PolarisLocalClient):
    """Async cloud client for Polaris 5X CU devices (fallback when local TCP is not possible)."""

    def __init__(
        self,
        email: str,
        password: str,
        serial: str = "",
        pin: str = "",
        name: str = "",
        android_id: Optional[str] = None,
        base_url: str = BASE_URL,
        timezone: str = "Europe@Rome",
        timeout: float = 15.0,
        retry_attempts: int = 3,
        retry_delay: float = 2.0,
        verbose: bool = False,
    ) -> None:
        """Initialize the Polaris cloud client.

        Args:
            email: Tecnosystemi account email.
            password: Tecnosystemi account password.
            serial: CU serial. Empty = login-only (use `get_devices` + `use_device`).
            pin: CU PIN (the cloud does not return it).
            name: CU name sent in write envelopes (defaults to the name from `GetCUState`).
            android_id: Stand-in for the app's ANDROID_ID: AES key seed and login `DeviceId`.
                Random if omitted.
            base_url: Backend URL (override for tests).
            timezone: Java zone id with "/" replaced by "@".
            timeout: Per-request HTTP timeout in seconds.
            retry_attempts: Total attempts per request, including the first.
            retry_delay: Delay between retries in seconds.
            verbose: Enable verbose debug logging (HTTP traffic, login excluded).
        """
        super().__init__(
            ip="cloud", pin=pin, device_id=f"polaris_cloud_{serial.upper() or 'account'}",
            timeout=timeout, retry_attempts=retry_attempts, retry_delay=retry_delay, verbose=verbose,
        )
        self.email = email
        self.password = password
        self.serial = serial.upper()
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.timezone = timezone
        self.android_id = android_id or uuid.uuid4().hex[:16]
        self._cipher = PolarisCipher(self.android_id)
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()  # the rolling token counter must advance one call at a time
        self._token = ""
        self._login_time = float("-inf")
        self.plants: list[dict[str, Any]] = []

    # ─── Connection management ──────────────────────────────────────

    async def connect(self) -> None:
        """Log in and, when a serial is set, fetch the first state (surfaces a wrong PIN)."""
        if self._connected:
            return
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        try:
            if not await self._login():
                raise TimeoutError(f"No reply from cloud backend {self.base_url}")
            self._connected = True
            if self.serial:
                await self.async_update()
        except BaseException:
            await self.disconnect()
            raise

    async def disconnect(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
        self._token = ""
        self._login_time = float("-inf")
        self._connected = False

    # ─── Public API (only what differs from PolarisLocalClient) ─────

    async def get_status(self) -> dict[str, Any]:
        """GET GetCUState: flat PascalCase CU state with `Zones`, parsed by the shared models."""
        res = await self._device_call("GET", "/api/v1/GetCUState",
                                      params={"cuSerial": self.serial, "PIN": self.pin})
        if res is None:
            raise TimeoutError(f"No reply from cloud for CU {self.serial}")
        # Cloud zone temps are always tenths ("215"); pre-scale so _parse_temp's >=100 heuristic
        # does not read values below 10.0 °C as whole degrees.
        for zone in res.get("Zones") or []:
            for key in ("Temp", "SetTemp"):
                try:
                    zone[key] = float(zone[key]) / 10
                except (KeyError, TypeError, ValueError):
                    pass
        return res

    async def get_zone_detail(self, zone_id: int) -> dict[str, Any]:
        raise PolarisApiError("stato_zona is local-only; cloud zones already carry Fancoil/Serranda")

    async def fetch_all_zone_details(self) -> dict[int, dict[str, Any]]:
        """No-op in cloud mode: `GetCUState` zones already include fancoil/serranda fields."""
        return {}

    async def get_plants(self) -> list[dict[str, Any]]:
        """GET GetPlants: plants and the devices bound to this account (all device types)."""
        res = await self._device_call("GET", "/api/v1/GetPlants")
        if res is None:
            raise TimeoutError("No reply from cloud for GetPlants")
        descr = res.get("ResDescr") or "[]"
        self.plants = json.loads(descr) if isinstance(descr, str) else descr
        return self.plants

    async def get_devices(self) -> list[dict[str, Any]]:
        """Flat list of the account's Polaris CUs (`LVDV_Type 0`): Serial, Name, ... + `PlantName`."""
        return [{**d, "PlantName": p.get("LVPL_Name", "")}
                for p in await self.get_plants() for d in p.get("ListDevices") or []
                if d.get("LVDV_Type") == DEVICE_TYPE_POLARIS]

    def use_device(self, serial: str, pin: str, name: str = "") -> None:
        """Point this logged-in session at another CU (one login, many devices). Clears cached state."""
        self.serial, self.pin, self.name = serial.upper(), pin, name
        self.device_id = f"polaris_cloud_{self.serial}"
        self._device, self._zones = None, []

    # ─── Cloud transport ────────────────────────────────────────────

    async def _send_command_with_retry(self, cmd: dict[str, Any]) -> Optional[dict[str, Any]]:
        """POST the local command to UpdateCUData / UpdateZonaData. The cloud only queues it."""
        body: dict[str, Any] = {
            "Serial": self.serial,
            "Name": self.name or (self._device.name if self._device else ""),
            "Pin": self.pin,
        }
        if cmd.get("c") == "upd_cu":
            if self._device is None:
                # upd_cu carries every CU field: without a read it would queue zeros (t_can, f_inv, ...)
                raise PolarisApiError("No CU state cached: call async_update() before writing")
            path = "/api/v1/UpdateCUData"
        elif cmd.get("c") == "upd_zona":
            path = "/api/v1/UpdateZonaData"
            body["ZoneId"] = cmd["id_zona"]
        else:
            raise PolarisApiError(f"Command '{cmd.get('c')}' is not available in cloud mode")
        body["Cmd"] = json.dumps(cmd)
        return await self._device_call("POST", path, body=body)

    async def _login(self) -> bool:
        """POST Login. False = no reply (transport); raises PolarisAuthError when rejected."""
        body = {
            "Username": self.email,
            "Password": self._cipher.encrypt(self.password),
            "DeviceId": self.android_id,
            "Timezone": self.timezone,
            "TokenPush": "",  # FCM token: none, so no push notifications
            "Platform": "fcm2",
        }
        status, res = await self._request("POST", _LOGIN_PATH, body=body, token=FIX_TOKEN, user=None)
        if status == 401:
            raise PolarisAuthError("Login unauthorized (HTTP 401)")
        if res is None:
            return False
        code = res.get("ResCode", -1)
        if code != 0:
            raise PolarisAuthError(_LOGIN_ERRORS.get(code, f"login failed (ResCode {code})"))
        self._token = res["Token"]
        self._login_time = time.monotonic()
        plants = res.get("ListPlants") or "[]"
        self.plants = json.loads(plants) if isinstance(plants, str) else plants
        return True

    async def _device_call(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, str]] = None,
        body: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """Authenticated call with retry and re-login.

        Returns the reply, or None when every attempt got no usable reply (same contract as
        the local transport). Raises PolarisApiError when the backend rejects the request and
        PolarisAuthError when the token is still refused on the last attempt.
        """
        if not self._session:
            raise PolarisApiError("Not connected to cloud")
        async with self._lock:
            unauthorized = False
            for attempt in range(1, self.retry_attempts + 1):
                if attempt > 1:
                    await asyncio.sleep(self.retry_delay)
                if time.monotonic() - self._login_time > SESSION_TTL and not await self._login():
                    unauthorized = False
                    continue
                try:
                    self._token = self._cipher.next_token(self._token)  # app keeps the bumped token too
                except ValueError:  # undecryptable token: the app sends null and gets a 401
                    unauthorized = True
                    self._login_time = float("-inf")
                    continue
                status, res = await self._request(method, path, params=params, body=body,
                                                  token=self._token, user=self.email)
                unauthorized = status == 401
                if unauthorized:
                    self._login_time = float("-inf")  # force re-login next attempt
                    continue
                if res is None:
                    continue
                code = res.get("ResCode", 0)  # GetCUState has no ResCode on success
                if code == 0:
                    return res
                if code == 2:
                    raise PolarisApiError("Wrong PIN")
                raise PolarisApiError(f"Cloud rejected {path} (ResCode {code})")
            if unauthorized:
                raise PolarisAuthError("Unauthorized (token rejected)")
            return None

    async def _request(
        self,
        method: str,
        path: str,
        token: str,
        user: Optional[str],
        params: Optional[dict[str, str]] = None,
        body: Optional[dict[str, Any]] = None,
    ) -> tuple[int, Optional[dict[str, Any]]]:
        """One HTTP call. Returns (status, parsed JSON); (0, None) on network error or timeout."""
        if not self._session:
            raise PolarisApiError("Not connected to cloud")
        basic = base64.b64encode(f"{user or 'UsrProAir'}:{BASIC_PWD}".encode()).decode()
        headers = {"Authorization": f"Basic {basic}", "Token": token}
        if method == "GET":
            headers["UserObj-Agent"] = "benincapp"
        log = self.verbose and path != _LOGIN_PATH  # login body/reply hold password and token
        if log:
            _LOGGER.debug("-> [%s] %s %s %s", self.device_id, method, path, body)
        try:
            async with self._session.request(method, self.base_url + path, params=params,
                                             headers=headers, json=body) as r:
                status, text = r.status, await r.text()
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            if self.verbose:
                _LOGGER.debug("[%s] %s %s failed: %s", self.device_id, method, path, err)
            return 0, None
        if log:
            _LOGGER.debug("<- [%s] %s %s", self.device_id, status, text)
        try:
            data = json.loads(text)
        except ValueError:
            return status, None
        return status, data if isinstance(data, dict) else None
