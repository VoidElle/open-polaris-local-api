# 🌡️ Open Polaris Local API (+ Cloud fallback)

> *Asynchronous Python library for Tecnosystemi Polaris 5X HVAC Control Unit devices*

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/github/v/release/VoidElle/open-polaris-local-api?label=version)](https://github.com/VoidElle/open-polaris-local-api/releases)
[![PyPI](https://img.shields.io/pypi/v/open-polaris-local-api)](https://pypi.org/project/open-polaris-local-api/)
[![Tests](https://github.com/VoidElle/open-polaris-local-api/actions/workflows/tests.yml/badge.svg)](https://github.com/VoidElle/open-polaris-local-api/actions/workflows/tests.yml)

**[Features](#-features) • [Installation](#-installation) • [Quick Start](#-quick-start) • [Documentation](#-documentation) • [Examples](#-examples) • [Scripts](#️-scripts) • [Testing](#-testing)**

---

## ✨ Features

### 🚀 **Performance**
- Built with **asyncio** for non-blocking operations
- Efficient TCP communication — short-lived connections per command (mirrors official app)
- **Automatic retry** on timeout or transient failure
- Compact `stato_r` polling with transparent fallback to full `stato`

### 🔄 **Reliability**
- **Auto-retry** with configurable attempts and delay
- Graceful fallback: `stato_r` → `stato` on older firmware
- Robust error decoding via bitmask for both CU and zone errors

### 🎯 **Developer Friendly**
- Type-safe dataclasses — `PolarisDevice` and `PolarisZone`
- Async context manager support
- Comprehensive logging with optional verbose mode
- Models parse local TCP replies and cloud (PascalCase) payloads

### 🔍 **Auto-Discovery**
- **Subnet scan** — finds all Polaris devices on your LAN without knowing their IPs
- Concurrent TCP probing with configurable timeout and concurrency
- Identifies devices by validating the Polaris protocol response

### 🎛️ **Full Control**
- CU-level: power, cooling mode, operating mode
- Zone-level: temperature setpoint, on/off, chrono mode, fan speed, shutter
- Human-readable error decoding (bitmask → error string list)

### ☁️ **Cloud Fallback**
- `PolarisCloudClient`: same API as `PolarisLocalClient`, over the official HTTPS cloud backend
- Use it **only when the local TCP connection is not a suitable flow** (e.g. CU on another network or port 1235 unreachable). Prefer local TCP otherwise: it is faster, needs no internet or account, and applies commands immediately
- Separate flow: the local client never calls the cloud, and the cloud client never touches the LAN
- Extra dependencies (`aiohttp`, `cryptography`) are installed automatically
- See [Cloud Client](#️-cloud-client)

---

## 📦 Installation

### pip (recommended)

```bash
pip install open-polaris-local-api
```

### Home Assistant integration

Add to your integration's `manifest.json`:

```json
"requirements": [
  "open-polaris-local-api==1.2.4"
]
```

### Manual

1. Clone this repository into your project
2. Ensure the `open_polaris_local_api/` folder is on your Python path
3. Import with `from open_polaris_local_api import PolarisLocalClient`

---

## 🚀 Quick Start

### Auto-Discovery

Find all Polaris devices on your network without knowing their IPs:

```python
import asyncio
from open_polaris_local_api import PolarisAutoDiscovery

async def main():
    ips = await PolarisAutoDiscovery.discover(pin="1234", subnet="192.168.1.0/24")
    print(f"Found {len(ips)} device(s): {ips}")
    # ["192.168.1.42"]

asyncio.run(main())
```

### Single Device

```python
import asyncio
from open_polaris_local_api import PolarisLocalClient

async def main():
    client = PolarisLocalClient(
        ip="192.168.1.100",
        pin="1234",
        device_id="living_room",
        verbose=True,
    )

    async with client:
        device, zones = await client.async_update()
        print(f"✓ {device.name} — {device.cooling_mode_name}, on={device.is_on}")

        for zone in zones:
            print(f"  Zone {zone.zone_id} '{zone.name}': {zone.current_temp}°C → {zone.set_temp}°C")

        # Turn on and set heating
        await client.set_heating_mode()
        await client.set_zone_temp(zones[0], 21.0)

if __name__ == "__main__":
    asyncio.run(main())
```

### Zone Control

```python
async def control_zones():
    async with PolarisLocalClient(ip="192.168.1.100", pin="1234") as client:
        _, zones = await client.async_update()

        # Turn off a zone
        await client.turn_zone_off(zones[0])

        # Set temperature on all zones
        for zone in zones:
            await client.set_zone_temp(zone, 20.0)
```

### CU-Level Control

```python
async def control_cu():
    async with PolarisLocalClient(ip="192.168.1.100", pin="1234") as client:
        # Switch to cooling mode (raffrescamento)
        await client.set_cooling_mode(1)

        # Switch to dehumidification
        await client.set_cooling_mode(2)

        # Switch to ventilation
        await client.set_cooling_mode(3)

        # Back to heating
        await client.set_heating_mode()

        # Full power off
        await client.turn_off()
```

---

## 📚 Documentation

- [Auto-Discovery](#-auto-discovery)
- [Configuration](#️-configuration)
- [Connection Management](#-connection-management)
- [Device Control (CU)](#️-device-control-cu)
- [Zone Control](#️-zone-control)
- [Data Models](#️-data-models)
- [Error Handling](#-error-handling)
- [Cloud Client](#️-cloud-client)
- [Library Structure](#-library-structure)
- [Official app protocol notes](docs/app/report.md): how the Tecnosystemi app talks to the CU, locally ([local-flows](docs/app/local-flows/README.md)) and through the cloud ([http-flows](docs/app/http-flows/README.md)), and how this library differs ([diff-app-api](docs/app/diff-app-api.md))

---

## 🔍 Auto-Discovery

Scans every host in the given subnet over TCP port 1235 and returns the IPs
of all responding Polaris devices. No prior knowledge of device IPs required.

```python
from open_polaris_local_api import PolarisAutoDiscovery

ips = await PolarisAutoDiscovery.discover(pin="1234", subnet="192.168.1.0/24")
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|:----:|:-------:|-------------|
| **`pin`** ⭐ | `str` | *required* | 🔐 Device PIN used for the probe |
| **`subnet`** ⭐ | `str` | *required* | 🌐 CIDR subnet to scan (e.g. `"192.168.1.0/24"`) |
| `port` | `int` | `1235` | 📡 TCP port to probe |
| `probe_timeout` | `float` | `1.5` | ⏱️ Per-host timeout in seconds |
| `max_concurrent` | `int` | `50` | ⚡ Maximum simultaneous TCP probes |
| `verbose` | `bool` | `False` | 📢 Enable debug logging |

### Notes

- A 254-host `/24` scan with defaults completes in roughly **8 seconds**
- A reply counts only if it has `fw_ver`, `serial` and `res` 1 or 4. Firmware without `stato_r` answers `res=4`; it is discovered only if that reply also carries `fw_ver` and `serial`
- Tune `probe_timeout` upward if devices are on a slow or congested network

---

## ⚙️ Configuration

### **Constructor Parameters**

| Parameter | Type | Default | Description |
|-----------|:----:|:-------:|-------------|
| **`ip`** ⭐ | `str` | *required* | 🌐 IP address of the Polaris CU device |
| **`pin`** ⭐ | `str` | *required* | 🔐 PIN code for authentication |
| `device_id` | `str` | `None` | 🏷️ Friendly identifier (auto-set to `polaris_{ip}:{port}` if omitted) |
| `port` | `int` | `1235` | 📡 TCP port on the device |
| `timeout` | `float` | `5.0` | ⏱️ Per-command socket timeout (seconds) |
| `retry_attempts` | `int` | `2` | 🔄 Total attempts per command (including the first) |
| `retry_delay` | `float` | `1.0` | ⏳ Delay between retries (seconds) |
| `verbose` | `bool` | `False` | 📢 Enable verbose debug logging |

---

## 🔌 Connection Management

### Connect

Verifies connectivity by performing an initial `async_update`. Sets `_connected=True` and populates cached device/zones state.

```python
await client.connect()
```

**Raises:** `TimeoutError` on failure. Connection errors (refused, reset) are retried inside the client and also end as `TimeoutError`.

### Disconnect

Marks the client as disconnected. TCP is stateless per-command, so no socket needs closing.

```python
await client.disconnect()
# or
await client.close()
```

### Context Manager (recommended)

```python
async with PolarisLocalClient(ip="192.168.1.100", pin="1234") as client:
    # automatically connects on enter, disconnects on exit
    device, zones = await client.async_update()
```

---

## 🖥️ Device Control (CU)

### Full Status Refresh

```python
device, zones = await client.async_update()
```

Returns a tuple of `(PolarisDevice, list[PolarisZone])` and updates the internal cache.

### Raw Status

```python
raw: dict = await client.get_status()
```

Tries `stato_r` first (compact), falls back to `stato` if unsupported (`res=4`).

### Power

```python
await client.turn_on()   # is_off=False
await client.turn_off()  # is_off=True
```

### Operating Mode

```python
await client.set_heating_mode()       # cooling=False, mode=0
await client.set_cooling_mode(1)      # raffrescamento
await client.set_cooling_mode(2)      # dehumidification
await client.set_cooling_mode(3)      # ventilation
```

### Full CU Update

```python
await client.update_cu(
    is_off=False,
    is_cooling=True,
    operating_mode=1,   # 0=heating, 1=cooling, 2=dehum, 3=vent
)
```

---

## 🌡️ Zone Control

### Convenience Methods

```python
await client.turn_zone_on(zone)
await client.turn_zone_off(zone)
await client.set_zone_temp(zone, 21.5)
```

### Full Zone Update

```python
await client.update_zone(
    zone,
    is_off=False,
    set_temp=21.0,
    is_crono=False,
    fancoil_set=2,
    serranda_set=3,
)
```

All parameters are optional; omitted values fall back to the zone's current state.

> **Note:** `set_temp` must be known (either from last `async_update` or provided explicitly). If neither is available, `ValueError` is raised.

### Shutter (Serranda)

```python
await client.set_zone_serranda(zone, 3)
```

Calls `update_zone(zone, serranda_set=value)` and updates `zone.serranda_set`. The value goes on the wire as `shu_set`/`fan_set` unchanged, except `7` (Auto), which is sent as `16`. The command only carries the value when `zone.serranda != -1`; if the zone also has a fancoil with a set-point, the fancoil value is sent instead.

Values used by the official app: `0` closed, `1`–`3` A1–A3, `4`–`6` Auto1–Auto3, `7` Auto.

### Zone Details (`stato_zona`)

`stato_r` / `stato` do not include every per-zone field. `stato_zona` returns `fan`, `fan_set`, `shu`, `shu_set`, `EV`, `EV_set`, `v` (zone firmware) and `m` (model).

```python
detail = await client.get_zone_detail(zone.zone_id)   # raw reply dict

details = await client.fetch_all_zone_details()        # {zone_id: detail}
```

- `get_zone_detail` raises `TimeoutError` when there is no reply, and `PolarisApiError` when the reply's `res` is not `1` (a missing `res` included), as the official app does.
- `fetch_all_zone_details` queries every zone in `client.zones` without errors (`num_error == 0`), waits 1 s before each request, and copies `shu`/`shu_set`/`fan`/`fan_set` into each zone's `serranda`/`serranda_set`/`fancoil`/`fancoil_set`. A zone that fails is logged and left out of the result; its cached values are not changed.
- `async_update()` does not call either method.

---

## 🗃️ Data Models

### `PolarisDevice`

Represents the Polaris Control Unit (CU).

| Property / Field | Type | Description |
|------------------|------|-------------|
| `serial` | `str` | Device serial number |
| `name` | `str` | Device name |
| `fw_ver` | `str` | Firmware version |
| `ip` | `str` | IP address |
| `is_off` | `bool` | Whether CU is off |
| `is_on` | `bool` (property) | Inverse of `is_off` |
| `is_cooling` | `bool` | Cooling active |
| `operating_mode` | `int` | 0=heating, 1=cooling, 2=dehum, 3=vent |
| `cooling_mode_name` | `str` (property) | Human-readable mode name |
| `t_can` | `int` | Canal temperature setpoint (°C) |
| `f_inv` | `int` | Winter function value (`f_inv`/`fi`); the app uses `-1` for absent, the library defaults to `0` |
| `f_est` | `int` | Summer function value (`f_est`/`fe`); same defaults as `f_inv` |
| `ir_present` | `int` | IR module present flag |
| `num_errors` | `int` | CU error bitmask |
| `has_error` | `bool` (property) | `num_errors != 0` |
| `active_errors` | `list[str]` (property) | Decoded error strings |
| `zones` | `list[PolarisZone]` | Not filled by `async_update` (stays `[]`); use the zones it returns or `client.zones` |

### `PolarisZone`

Represents a single HVAC zone.

| Property / Field | Type | Description |
|------------------|------|-------------|
| `zone_id` | `int` | Zone ID |
| `name` | `str` | Zone name |
| `current_temp` | `float \| None` | Current temperature (°C) |
| `set_temp` | `float \| None` | Temperature setpoint (°C) |
| `is_off` | `bool` | Whether zone is off |
| `is_on` | `bool` (property) | Inverse of `is_off` |
| `is_cooling` | `bool` | Cooling active |
| `fancoil` | `int` | Fan coil current speed (-1 = not installed) |
| `fancoil_set` | `int` | Fan coil setpoint (-1 = not installed) |
| `serranda` | `int` | Shutter position (-1 = not installed) |
| `serranda_set` | `int` | Shutter setpoint (-1 = not installed) |
| `ev` | `int` | `EV` field, raw (default `0`) |
| `man_crono` | `int` | `man_crono` field, raw (default `0`) |
| `is_crono_mode` | `bool` | Chrono (scheduled) mode active |
| `is_master` | `bool` | Zone is master |
| `humidity` | `float \| None` | Current humidity (%) |
| `set_humidity` | `float \| None` | Humidity setpoint (%) |
| `num_error` | `int` | Zone error bitmask |
| `has_error` | `bool` (property) | `num_error != 0` |
| `active_errors` | `list[str]` (property) | Decoded error strings |
| `c_badge` / `c_win` | `Any` | Badge and window contact fields, raw |
| `raw_data` | `dict` | Original zone payload |

Both models accept both **local TCP** (snake_case, ridotto, full) and **cloud API** (PascalCase) response formats via the `from_local()` factory method.

---

## ⚠️ Error Handling

### Exceptions

| Exception | Raised by | When |
|---|---|---|
| `TimeoutError` | `connect`, `async_update`, `get_status`, `get_zone_detail` | No reply after all retries |
| `PolarisApiError` | `get_zone_detail` | `stato_zona` reply with `res` other than `1` |
| `PolarisAuthError` | `PolarisCloudClient` (any call) | Cloud only: login rejected or token refused. Subclass of `PolarisApiError`, import from `open_polaris_local_api.cloud` |
| `ValueError` | `update_zone`, `PolarisAutoDiscovery.discover` | `set_temp` unknown; invalid or non-IPv4 subnet |

Write commands (`update_zone`, `update_cu` and the helpers built on them) do not raise when the device does not reply: they log a warning.

```python
from open_polaris_local_api import PolarisApiError

try:
    async with PolarisLocalClient(ip="192.168.1.100", pin="1234") as client:
        device, zones = await client.async_update()
        detail = await client.get_zone_detail(zones[0].zone_id)
except TimeoutError:
    print("Device unreachable")
except PolarisApiError as e:
    print(f"Device returned an error: {e}")
```

### Device / Zone Errors

```python
device, zones = await client.async_update()

if device.has_error:
    print(f"CU errors: {device.active_errors}")

for zone in zones:
    if zone.has_error:
        print(f"Zone '{zone.name}' errors: {zone.active_errors}")
```

---

## ☁️ Cloud Client

> **Note:** use the cloud client only if the local TCP connection is not a suitable flow. Local TCP is the primary, recommended path: it works offline, needs no account, has lower latency and applies commands immediately. The cloud adds a dependency on the vendor backend, requires internet and credentials, and applies commands asynchronously.

`PolarisCloudClient` subclasses `PolarisLocalClient`, so `async_update`, `update_cu`, `update_zone`, `turn_on`/`turn_off`, `set_cooling_mode`, `set_heating_mode`, `set_zone_temp`, `turn_zone_on`/`turn_zone_off` and `set_zone_serranda` are inherited and build the same `upd_cu` / `upd_zona` commands. Only the transport changes: TCP is replaced by `https://proair.azurewebsites.net`.

```python
from open_polaris_local_api.cloud import PolarisCloudClient

async with PolarisCloudClient("me@x.com", "password", serial="SER123", pin="1234") as cloud:
    device, zones = await cloud.async_update()     # GET GetCUState
    await cloud.turn_on()                          # POST UpdateCUData
    await cloud.set_zone_temp(zones[0], 21.0)      # POST UpdateZonaData
```

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| **`email`** ⭐ | `str` | *required* | Tecnosystemi account email |
| **`password`** ⭐ | `str` | *required* | Tecnosystemi account password |
| `serial` | `str` | `""` | CU serial; empty = login only (use `get_devices` + `use_device`) |
| `pin` | `str` | `""` | CU PIN |
| `name` | `str` | `""` | CU name sent with writes (defaults to the name from `GetCUState`) |
| `android_id` | `str` | random | Stand-in for the app's ANDROID_ID (AES key seed, login `DeviceId`) |
| `base_url` | `str` | `https://proair.azurewebsites.net` | Backend URL |
| `timezone` | `str` | `"Europe@Rome"` | Java zone id with `/` replaced by `@` |
| `timeout` | `float` | `15.0` | Per-request HTTP timeout (seconds) |
| `retry_attempts` | `int` | `3` | Total attempts per request (including the first) |
| `retry_delay` | `float` | `2.0` | Delay between retries (seconds) |
| `verbose` | `bool` | `False` | Log every HTTP request/response (contains email and PIN; login request and reply excluded) |

### Account Methods

```python
plants = await cloud.get_plants()       # plants with their devices (also stored in cloud.plants)
devices = await cloud.get_devices()     # flat list of Polaris CUs (LVDV_Type 0), each with "PlantName"
cloud.use_device("SER456", "5678")      # point the same session at another CU (the cloud does not return PINs)
device, zones = await cloud.async_update()  # required after use_device, before any CU write
```

Differences vs local:
- `connect()` logs in and, when `serial` is set, runs a first `async_update()` (a wrong PIN raises `PolarisApiError` here).
- Writes are queued by the cloud; the CU applies them later (the app warns "within 10 minutes" for firmware < 4). Poll `async_update()` to see the result.
- `get_zone_detail` raises `PolarisApiError` and `fetch_all_zone_details` returns `{}`: `stato_zona` is local-only, and `GetCUState` zones already carry `Fancoil`/`Serranda`.
- `update_cu` (and `turn_on`/`turn_off`/mode helpers) raises `PolarisApiError` when no CU state is cached (e.g. right after `use_device`): `upd_cu` carries every CU field, so call `async_update()` first.
- `device.ip` holds the CU's LAN IP reported by the cloud: use it to switch back to `PolarisLocalClient` when the LAN is reachable.
- The session lasts about 1 h; the client logs in again after 55 min or on HTTP 401.
- Errors: `PolarisAuthError` (subclass of `PolarisApiError`) for rejected credentials or a token still refused after re-login; `PolarisApiError` for a wrong PIN or another non-zero `ResCode`; `TimeoutError` when the backend does not reply. As in local mode, a write that gets no reply logs a warning instead of raising.
- The Tecnosystemi backend allows one session per account at a time. While the client is logged in, the official app shows an alert and stops working.
- Not implemented: schedules (`GetTW`/`UpdateTW`), CU clock (`UpdateCUDatetime`), restore (`SendRestoreCmd`), provisioning.

> Unverified against the real backend: the server accepting a client-generated `DeviceId`, an empty `TokenPush`, and the exact `Timezone` format. Tested only against a fake backend built from the decompiled app.

Protocol: [`docs/app/http-flows/`](docs/app/http-flows/). Cloud examples: [`examples/cloud/`](examples/cloud/), documented in [`examples/README.md`](examples/README.md).

---

## 📦 Library Structure

```
open-polaris-local-api/
├── scripts/
│   ├── bump_version.sh              # Bump version across all files
│   └── run_tests.sh                 # Run the full test suite
├── examples/
│   ├── README.md                    # Examples documentation
│   ├── local/                       # Local TCP examples
│   │   ├── basic_control.py         # Connect, read status, control a single device
│   │   ├── auto_discovery.py        # Discover devices then read their status
│   │   ├── multi_device.py          # Concurrent control of multiple devices
│   │   └── monitoring.py            # Continuous polling with error alerts
│   └── cloud/                       # Cloud examples (PolarisCloudClient)
│       ├── _common.py               # Shared helpers
│       ├── login.py                 # Login only
│       ├── list_devices.py          # Polaris CUs of the account
│       ├── basic_cloud.py           # Status, heating mode
│       ├── simple_actions.py        # One-shot CLI actions
│       ├── monitor_cloud.py         # Polling with diffs and backoff
│       └── multi_device_cloud.py    # All CUs of the account
├── docs/app/                        # Official app protocol notes and app-vs-library diff
├── open_polaris_local_api/
│   ├── __init__.py                  # exports: PolarisLocalClient, PolarisApiError, PolarisDevice, PolarisZone, PolarisAutoDiscovery
│   ├── client.py                    # PolarisLocalClient, PolarisApiError
│   ├── models.py                    # PolarisDevice, PolarisZone dataclasses + parsing helpers
│   ├── polaris_auto_discovery.py    # PolarisAutoDiscovery — subnet scanner
│   └── cloud/
│       ├── __init__.py              # exports: PolarisCloudClient, PolarisAuthError
│       ├── polaris_cloud_client.py  # HTTPS transport, subclass of PolarisLocalClient
│       ├── crypto.py                # PolarisCipher (password and rolling token)
│       └── exceptions.py            # PolarisAuthError
└── tests/
    ├── local/                       # Local TCP tests
    │   ├── test_models.py
    │   ├── test_polaris_client.py
    │   └── test_polaris_auto_discovery.py
    └── cloud/                       # Cloud tests (fake backend, no network)
        ├── test_cloud_client.py
        └── test_examples.py         # Runs examples/cloud scripts against the fake backend
```

---

## 💡 Examples

Ready-to-run example scripts are available in the [`examples/`](examples/) directory.
See [`examples/README.md`](examples/README.md) for full documentation and usage instructions.

---

## 🛠️ Scripts

Utility scripts live in the [`scripts/`](scripts/) directory and must be run from the repo root.

### `scripts/bump_version.sh`

Keeps all version references in sync across `pyproject.toml` and `README.md` in one command.

```bash
./scripts/bump_version.sh patch     # X.Y.Z → X.Y.(Z+1)
./scripts/bump_version.sh minor     # X.Y.Z → X.(Y+1).0
./scripts/bump_version.sh major     # X.Y.Z → (X+1).0.0
./scripts/bump_version.sh X.Y.Z     # set an explicit version
./scripts/bump_version.sh           # interactive menu
```

### `scripts/run_tests.sh`

Runs the full unit test suite with verbose output.

```bash
./scripts/run_tests.sh
```

---

## 🧪 Testing

```bash
pip install -e .          # aiohttp + cryptography, needed by tests/cloud
./scripts/run_tests.sh    # or: python3 -W all -m unittest discover -s tests -t . -v
```

Cloud tests run against a local fake backend; they never contact the real cloud.

---

## 📋 Requirements

- **Python 3.11+**
- **asyncio** support
- **Local network access** to the Polaris CU device (TCP port 1235)
- `aiohttp` and `cryptography` (installed automatically; used by the cloud client)
- Cloud client (`PolarisCloudClient`): internet access and a Tecnosystemi cloud account, no local network access needed

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## 🆘 Support

- 🐛 **Issues**: [Report a bug](https://github.com/VoidElle/open-polaris-local-api/issues)
