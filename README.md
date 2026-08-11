# 🌡️ Open Polaris Local API

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
- Supports both local TCP (snake_case) and cloud API (PascalCase) response formats

### 🔍 **Auto-Discovery**
- **Subnet scan** — finds all Polaris devices on your LAN without knowing their IPs
- Concurrent TCP probing with configurable timeout and concurrency
- Identifies devices by validating the Polaris protocol response

### 🎛️ **Full Control**
- CU-level: power, cooling mode, operating mode
- Zone-level: temperature setpoint, on/off, chrono mode, fan speed, shutter
- Human-readable error decoding (bitmask → error string list)

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
  "open-polaris-local-api==1.2.2"
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
- [Library Structure](#-library-structure)

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
- Devices running older firmware (no `stato_r` support) are still discovered — a `res=4` reply is enough to confirm a Polaris device
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
| `retry_attempts` | `int` | `2` | 🔄 Number of retry attempts on failure |
| `retry_delay` | `float` | `1.0` | ⏳ Delay between retries (seconds) |
| `verbose` | `bool` | `False` | 📢 Enable verbose debug logging |

---

## 🔌 Connection Management

### Connect

Verifies connectivity by performing an initial `async_update`. Sets `_connected=True` and populates cached device/zones state.

```python
await client.connect()
```

**Raises:** `TimeoutError` or `ConnectionError` on failure.

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
| `f_inv` | `int` | Winter fan speed |
| `f_est` | `int` | Summer fan speed |
| `ir_present` | `int` | IR module present flag |
| `num_errors` | `int` | CU error bitmask |
| `has_error` | `bool` (property) | `num_errors != 0` |
| `active_errors` | `list[str]` (property) | Decoded error strings |
| `zones` | `list[PolarisZone]` | Zones (populated by `async_update`) |

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
| `is_crono_mode` | `bool` | Chrono (scheduled) mode active |
| `is_master` | `bool` | Zone is master |
| `humidity` | `float \| None` | Current humidity (%) |
| `set_humidity` | `float \| None` | Humidity setpoint (%) |
| `num_error` | `int` | Zone error bitmask |
| `has_error` | `bool` (property) | `num_error != 0` |
| `active_errors` | `list[str]` (property) | Decoded error strings |

Both models accept both **local TCP** (snake_case, ridotto, full) and **cloud API** (PascalCase) response formats via the `from_local()` factory method.

---

## ⚠️ Error Handling

### `PolarisApiError`

Raised on communication failures:

```python
from open_polaris_local_api import PolarisApiError

try:
    async with PolarisLocalClient(ip="192.168.1.100", pin="1234") as client:
        device, zones = await client.async_update()
except TimeoutError:
    print("Device unreachable")
except PolarisApiError as e:
    print(f"Communication error: {e}")
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

## 📦 Library Structure

```
open-polaris-local-api/
├── scripts/
│   ├── bump_version.sh              # Bump version across all files
│   └── run_tests.sh                 # Run the full test suite
├── examples/
│   ├── README.md                    # Examples documentation
│   ├── basic_control.py             # Connect, read status, control a single device
│   ├── auto_discovery.py            # Discover devices then read their status
│   ├── multi_device.py              # Concurrent control of multiple devices
│   └── monitoring.py                # Continuous polling with error alerts
├── open_polaris_local_api/
│   ├── __init__.py                  # exports: PolarisLocalClient, PolarisApiError, PolarisDevice, PolarisZone, PolarisAutoDiscovery
│   ├── client.py                    # PolarisLocalClient, PolarisApiError
│   ├── models.py                    # PolarisDevice, PolarisZone dataclasses + parsing helpers
│   └── polaris_auto_discovery.py    # PolarisAutoDiscovery — subnet scanner
└── tests/
    ├── test_models.py
    ├── test_polaris_client.py
    └── test_polaris_auto_discovery.py
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
./scripts/bump_version.sh patch     # 1.0.1 → 1.0.2
./scripts/bump_version.sh minor     # 1.0.1 → 1.1.0
./scripts/bump_version.sh major     # 1.0.1 → 2.0.0
./scripts/bump_version.sh 1.2.3     # set an explicit version
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
./scripts/run_tests.sh
```

---

## 📋 Requirements

- **Python 3.11+**
- **asyncio** support
- **Local network access** to the Polaris CU device (TCP port 1235)
- No third-party dependencies — stdlib only

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
