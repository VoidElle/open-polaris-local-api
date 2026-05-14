# Coding Agent — open-polaris-local-api

## Project Overview
Async Python library (asyncio, Python 3.11+) for controlling Tecnosystemi Polaris 5X HVAC Control Unit (CU) devices over local TCP. Used as a local API client, commonly integrated with Home Assistant.

## Architecture
- **`PolarisLocalClient`** (`polaris_client.py`) — main public API. One instance per device.
- **`PolarisDevice`** (`models.py`) — dataclass representing the CU state (power, mode, errors, zones list).
- **`PolarisZone`** (`models.py`) — dataclass representing a single HVAC zone (temp, setpoints, fan, shutter, errors).
- **`PolarisApiError`** (`polaris_client.py`) — base exception for communication failures.

## TCP Protocol
- JSON payloads over **raw TCP socket** on **port 1235**
- Each command opens its own short-lived connection and closes after receiving the response (mirrors `MySocket.sendAndReceive` in the official APK)
- Command key is **`"c"`** — not `"cmd"`. No `idp` or `frm` envelope needed
- Commands:
  - `stato_r` — compact/ridotto status poll (preferred for local polling)
  - `stato` — full status (fallback when device returns `res=4` for `stato_r`)
  - `upd_zona` — update a zone's settings
  - `upd_cu` — update CU-level settings
- `"stato_sync"` is a cloud/HTTP command — **never send over TCP**

## Model Parsing
- Both `PolarisDevice` and `PolarisZone` use `from_local(data)` as the single factory method
- `from_local` handles three response dialects transparently:
  1. **Local ridotto** (e.g., `off`, `cl`, `cl_m`, `fi`, `fe`, `tc`)
  2. **Local full** (e.g., `is_off`, `is_cool`, `cool_mod`, `f_inv`, `f_est`, `t_can`)
  3. **Cloud/PascalCase** (e.g., `IsOFF`, `IsCooling`, `OperatingModeCooling`, `TempCan`)
- `from_api()` on both models delegates to `from_local()` for backward compatibility
- Temperature encoding: values ≥ 100 are integer-encoded (e.g., 195 = 19.5°C). Use `_parse_temp()`
- `t_can` is transmitted as `°C × 10`; divide by 10 on parse, multiply by 10 on send
- Error fields are integer bitmasks (LSB = bit 0); decode with `_decode_error_bitmask(mask, messages)`

## Coding Conventions
- All I/O methods are `async`
- Raise `TimeoutError` (stdlib) when device is unreachable after all retries
- Raise `ValueError` for invalid arguments (e.g., `update_zone` with no known `set_temp`)
- `verbose` flag gates all debug logging via `_LOGGER.debug`
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

## Key Constraints
- Each TCP call opens and closes its own socket — no persistent connection
- Never send `stato_sync` over TCP (cloud-only command)
- `fan_set` and `shu_set` in `upd_zona` must always be sent together with the same value (per APK protocol)
- Python 3.11+ required
- No third-party dependencies — stdlib only

## Testing
- No automated test suite currently present
- Manual testing: enable `verbose=True` and inspect DEBUG log output for TCP send/receive traces
- Verify both `stato_r` fallback path (res=4 → stato) and normal path work against the device
