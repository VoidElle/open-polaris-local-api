# 💡 Examples

Ready-to-run scripts that demonstrate the main features of the `open-polaris-local-api` library.
Every script accepts CLI arguments — no code editing required.

---

## Scripts

### [`basic_control.py`](basic_control.py)

Connects to a single device, prints its current status (device + all zones), turns it on, and sets heating mode.

```bash
python3 examples/local/basic_control.py --ip 192.168.1.100 --pin 1234
```

---

### [`auto_discovery.py`](auto_discovery.py)

Scans a subnet for Polaris devices, then connects to each discovered device and reads its status.

> ⚠️ All devices on the network must share the same PIN to be discovered in a single scan.

```bash
python3 examples/local/auto_discovery.py --subnet 192.168.1.0/24 --pin 1234

# Longer timeout for slower networks
python3 examples/local/auto_discovery.py --subnet 192.168.1.0/24 --pin 1234 --timeout 3.0
```

---

### [`multi_device.py`](multi_device.py)

Controls multiple Polaris CU devices concurrently.
Connects all devices at once, reads their statuses in parallel, then sets a uniform mode across all of them.

```bash
python3 examples/local/multi_device.py --pin 1234 --ips 192.168.1.100 192.168.1.101
```

---

### [`monitoring.py`](monitoring.py)

Continuously polls a device and prints a status report. Alerts on CU or zone errors.

```bash
python3 examples/local/monitoring.py --ip 192.168.1.100 --pin 1234

# Custom polling interval
python3 examples/local/monitoring.py --ip 192.168.1.100 --pin 1234 --interval 10
```

Sample output:
```
[14:32:01]  ✅ Healthy  🟢 ON
  Device : Living Room CU  (fw: 1.0)
  Mode   : Heating
  Canal  : 22°C
  Zone 1 'Living Room': ON  21.5°C → 22.0°C
  Zone 2 'Bedroom':     ON  20.0°C → 21.0°C
```

---

## Common arguments (local examples, in `examples/local/`)

| Argument | Used by | Description |
|----------|---------|-------------|
| `--ip` | all except `auto_discovery` | Device IP address |
| `--pin` | all | Device PIN |
| `--subnet` | `auto_discovery` | CIDR range to scan (e.g. `192.168.1.0/24`) |
| `--ips` | `multi_device` | Space-separated list of IP addresses |
| `--timeout` | `auto_discovery` | Per-host probe timeout in seconds (default: `1.5`) |
| `--interval` | `monitoring` | Polling interval in seconds (default: `30`) |

---

## Cloud examples (in `examples/cloud/`)

These use `PolarisCloudClient` and need `aiohttp` and `cryptography` (installed with the package). Use them only when the local TCP connection is not possible. Credentials come from flags (`--email`, `--password`, `--serial`, `--pin`) or the env vars `POLARIS_EMAIL`, `POLARIS_PASSWORD`, `POLARIS_SERIAL`, `POLARIS_PIN`. Add `--verbose` to log HTTP traffic.

| Example | What |
|---------|------|
| [`login.py`](cloud/login.py) | Login only, prints plant/device counts |
| [`list_devices.py`](cloud/list_devices.py) | Polaris CUs of the account (`--json` for raw plants). Cloud gives no PINs |
| [`basic_cloud.py`](cloud/basic_cloud.py) | Status (CU + zones), heating mode |
| [`simple_actions.py`](cloud/simple_actions.py) | One-shot CLI: `status`, `on`, `off`, `heat`, `cool N`, `zone-temp T --zone N`, `zone-on`, `zone-off` |
| [`monitor_cloud.py`](cloud/monitor_cloud.py) | Poll every 5 s, print diffs, backoff on errors |
| [`multi_device_cloud.py`](cloud/multi_device_cloud.py) | Every CU of the account on one login (`use_device`), bulk `--turn` / `--heat` |

Cloud writes are queued: the CU applies them later, and the next poll shows the result.

Warning: these examples hit the real cloud. Use your own account.
