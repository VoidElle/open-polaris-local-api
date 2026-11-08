# Coding Agent — open-polaris-local-api

## Project Overview
Async Python library (asyncio, Python 3.11+) for controlling Tecnosystemi Polaris 5X HVAC Control Unit (CU) devices. Primary path is local TCP; `PolarisCloudClient` is a fallback over the vendor's HTTPS backend, used only when a local connection is not possible. Commonly integrated with Home Assistant.

## Architecture
- **`PolarisLocalClient`** (`client.py`) — main public API. One instance per device.
- **`PolarisDevice`** (`models.py`) — dataclass representing the CU state (power, mode, errors, zones list).
- **`PolarisZone`** (`models.py`) — dataclass representing a single HVAC zone (temp, setpoints, fan, shutter, errors).
- **`PolarisApiError`** (`client.py`) — raised when the device replies with an error (locally only `get_zone_detail`, on `res != 1`; in cloud mode also wrong PIN / non-zero `ResCode`).
- **`cloud/`** — cloud fallback, imported from `open_polaris_local_api.cloud` (not re-exported at top level). Separate flow: `PolarisLocalClient` never calls it and it never touches the LAN:
  - `PolarisCloudClient` (`polaris_cloud_client.py`) — subclass of `PolarisLocalClient`; overrides `connect`, `disconnect`, `get_status`, `get_zone_detail`, `fetch_all_zone_details` and `_send_command_with_retry`. Adds `get_plants`, `get_devices` (Polaris only, `LVDV_Type 0`), `use_device`
  - `PolarisCipher` (`crypto.py`) — app AES scheme: key = SHA-256(`android_id[:8]` + `ns91wr48`), CBC, zero IV; rolling token via `next_token`
  - `PolarisAuthError` (`exceptions.py`) — subclass of `PolarisApiError`; login rejected or token still refused (HTTP 401) on the last attempt

## TCP Protocol
- JSON payloads over **raw TCP socket** on **port 1235**
- Each command opens its own short-lived connection and closes after receiving the response (mirrors `MySocket.sendAndReceive` in the official APK)
- Command key is **`"c"`** — not `"cmd"`. No `idp` or `frm` envelope needed
- Commands:
  - `stato_r` — compact/ridotto status poll (preferred for local polling)
  - `stato` — full status (fallback when device returns `res=4` for `stato_r`)
  - `stato_zona` — per-zone details (`fan`, `fan_set`, `shu`, `shu_set`, `EV`, `EV_set`, `v`, `m`); `get_zone_detail` / `fetch_all_zone_details`, never called by `async_update`
  - `upd_zona` — update a zone's settings
  - `upd_cu` — update CU-level settings
- `"stato_sync"` is a cloud/HTTP command — **never send over TCP**

## Cloud Protocol
Reverse-engineered from the official app; spec in `docs/app/http-flows/` (read it before touching `cloud/`).
- One backend `https://proair.azurewebsites.net` (`aiohttp`); `/apiTS/*` = account, `/api/*` = devices
- Auth: Basic `<email>:PwdProAir` (`UsrProAir` before login) + `Token` header. Login uses `FIX_TOKEN`; every later call bumps the rolling token counter (decrypt `<text>_<n>`, n+1, re-encrypt) under `self._lock`
- Session is 1 h hard from login, no refresh: client re-logs in after `SESSION_TTL` (55 min) or on HTTP 401
- `GetCUState?cuSerial=&PIN=` (GET): flat PascalCase CU JSON with `Zones`, **no `ResCode` on success**; parsed by the shared `from_local`. `get_status` pre-scales zone `Temp`/`SetTemp` (always tenths) to °C so `_parse_temp`'s `>= 100` heuristic does not misread values below 10.0 °C
- Writes: `UpdateCUData` `{Serial, Name, Pin, Cmd}` and `UpdateZonaData` `{Serial, Name, Pin, ZoneId, Cmd}`; `Cmd` = the local `upd_cu` / `upd_zona` dict JSON-encoded as a string; `Name` is the CU name. Reply `{ResCode, ResDescr}`; HTTP 400 carries the same body. `ResCode 0` OK, `2` wrong PIN
- The cloud only queues writes (no CU ack); results show in the next `GetCUState`. Never add `?create_command=false`: that is for commands already delivered over TCP, and the flows stay separate
- Cloud `upd_cu` refuses to run with `_device is None` (raises `PolarisApiError`): it would queue zeros for `t_can`/`f_inv`/`f_est`. `use_device` clears the cache, so callers must `async_update()` first
- Transport contract matches local: `_device_call` returns `None` when no attempt got a usable reply (`get_status` then raises `TimeoutError`, writes log a warning); logical rejections raise

## Model Parsing
- Both `PolarisDevice` and `PolarisZone` use `from_local(data)` as the single factory method
- `from_local` handles three response dialects transparently:
  1. **Local ridotto** (e.g., `off`, `cl`, `cl_m`, `fi`, `fe`, `tc`)
  2. **Local full** (e.g., `is_off`, `is_cool`, `cool_mod`, `f_inv`, `f_est`, `t_can`)
  3. **Cloud/PascalCase** (e.g., `IsOFF`, `IsCooling`, `OperatingModeCooling`, `TempCan`, CU `Errors` bitmask, zone `IsMaster`)
- `PolarisZone.from_api()` and `PolarisDevice.from_get_home()` delegate to `from_local()` for backward compatibility
- Temperature encoding: values ≥ 100 are integer-encoded (e.g., 195 = 19.5°C). Use `_parse_temp()`
- `t_can` is transmitted as `°C × 10`; divide by 10 on parse, multiply by 10 on send
- Error fields are integer bitmasks (LSB = bit 0); decode with `_decode_error_bitmask(mask, messages)`

## Coding Conventions
- All I/O methods are `async`
- Raise `TimeoutError` (stdlib) when device is unreachable after all retries
- `res` handling: `get_zone_detail` mirrors the app (only `res == 1` is valid, missing `res` included, otherwise `PolarisApiError`). `get_status` only checks `res == 4` on `stato_r` to fall back to `stato`; it does not reject other codes
- Write commands log a warning on no reply; they do not raise
- Raise `ValueError` for invalid arguments (e.g., `update_zone` with no known `set_temp`)
- `verbose` flag gates the transport and detail debug logs; `async_update` (debug) and `update_zone`/`update_cu` (info) always log a summary line
- New commands follow the `_send_command_with_retry` → `_send_and_receive` pattern
- Zone fan/shutter: value `7` maps to `16` on the wire (auto-speed sentinel)
- When both fancoil and serranda are present, fancoil takes priority (`lastFancoil=True` default in APK)
- Guard write methods: cached `_device` may be `None` — always use `dev.field if dev else fallback`

## Adding a New Command
1. Build `cmd` dict with `"c": "<command_name>"`, `"pin": self.pin`, and required fields
2. Call `await self._send_command_with_retry(cmd)` — returns parsed dict or `None`
3. If `None` returned, log a warning (device may not reply to all write commands)
4. For read commands: parse result into models using `from_local()`
5. Do not create new socket handling code — always go through `_send_and_receive`
6. Go through `_send_command_with_retry` or `PolarisCloudClient` will not inherit the command. A new write needs a cloud endpoint mapping in `PolarisCloudClient._send_command_with_retry` (unmapped commands raise `PolarisApiError`); a new read needs its own cloud override

## Key Constraints
- Each TCP call opens and closes its own socket — no persistent connection
- Never send `stato_sync` over TCP (cloud-only command)
- `fan_set` and `shu_set` in `upd_zona` must always be sent together with the same value (per APK protocol)
- `PolarisLocalClient` changes ripple into `PolarisCloudClient`: keep `_send_command_with_retry(cmd)`, `get_status()` and the overridden signatures in sync, and check `tests/cloud/`
- Local is the primary path: do not make the cloud a default or automatic route, and do not import `cloud/` from local modules
- Never log credentials: `verbose` HTTP logging skips the login request and reply (password, token)
- Python 3.11+ required
- Runtime deps: `aiohttp`, `cryptography` (cloud only); the local modules stay stdlib-only

## Testing
- Unit tests in `tests/` (`unittest`, `IsolatedAsyncioTestCase`): `tests/local/` TCP, `tests/cloud/` cloud client. Install with `pip install -e .` first (otherwise `tests/cloud` fails to import). Run `./scripts/run_tests.sh` or `python3 -W all -m unittest discover -s tests -t . -v` (CI command)
- Mock the local transport by replacing `client._send_command_with_retry` with a fake coroutine
- Mock a `StreamWriter` as `MagicMock` with only `drain`/`wait_closed` as `AsyncMock` (`write`/`close` are sync; an `AsyncMock` writer emits `RuntimeWarning`). The suite must run with zero warnings under `-W all`
- Cloud tests run against a local fake backend (`aiohttp.test_utils.TestServer` + `base_url`) that enforces the rolling-token counter; never hit the real backend in tests
- `tests/cloud/test_examples.py` runs each `examples/cloud/` script (except the endless `monitor_cloud.py`) against that backend: update it when an example's CLI or output changes
- Manual testing: enable `verbose=True` and inspect DEBUG log output for TCP send/receive traces
- Verify both `stato_r` fallback path (res=4 → stato) and normal path work against the device
