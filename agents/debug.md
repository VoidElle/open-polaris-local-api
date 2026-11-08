# Debug Agent — open-polaris-local-api

## Purpose
Diagnose issues in the async TCP communication stack of this Polaris 5X CU device library, and in the cloud fallback (`open_polaris_local_api.cloud`).

## Common Failure Modes

### Device unreachable / TimeoutError
**Symptom:** `async_update()` or `get_status()` raises `TimeoutError`.  
**Cause:** Device offline, wrong IP, wrong PIN, or firewall blocking TCP port 1235.  
**Fix:** Verify IP/PIN; test raw connectivity with `nc -zv <ip> 1235`; check `timeout` and `retry_attempts` constructor params.

### `stato_r` not supported (res=4 fallback)
**Symptom:** With `verbose=True`, log shows `"stato_r not supported (res=4), falling back to stato"`.  
**Cause:** Older firmware doesn't implement the compact ridotto command.  
**Fix:** Normal behaviour — client automatically retries with full `stato`. No action needed.

### Zone update silently ignored (no response)
**Symptom:** `update_zone()` completes but device doesn't react; WARNING log `"No response for upd_zona"`.  
**Cause:** Device doesn't always reply to write commands. Command may still have been applied.  
**Fix:** Call `async_update()` after the write to confirm new state; increase `retry_attempts` if network is lossy.

### `ValueError` on `update_zone`
**Symptom:** `"Cannot update zone X: no target temperature known"`.  
**Cause:** `set_temp` not provided and zone's `set_temp` field is `None` (no prior `async_update`).  
**Fix:** Always call `async_update()` before write commands, or pass `set_temp` explicitly.

### Wrong temperature values parsed
**Symptom:** Temperatures display as 195°C instead of 19.5°C (or vice versa).  
**Cause:** Integer-encoding mismatch — values ≥ 100 represent `°C × 10` in some response formats.  
**Fix:** Parsing handled automatically by `_parse_temp()`. If values are wrong, check which response dialect the device is sending and verify the field name matches (ridotto vs full vs cloud).

### Fan/shutter not updating
**Symptom:** `update_zone` completes but fan speed or shutter unchanged.  
**Cause:** `fancoil_set` or `serranda_set` is `-1` (hardware not installed), or value `7` needs mapping to `16`.  
**Fix:** Check `zone.fancoil` / `zone.serranda` — if `-1`, hardware not present. Value `7` (auto) maps to `16` on wire; this is handled automatically in `update_zone`.

### CU update no-op (device state unchanged)
**Symptom:** `update_cu()` returns normally but device power/mode unchanged.  
**Cause:** `_device` is `None` — no prior `async_update()` — so all effective values fall back to defaults (off=False, cooling=False, mode=0).  
**Fix:** Always call `async_update()` (or `connect()`) before any write to populate `_device`.

### Error bitmask showing unexpected errors
**Symptom:** `active_errors` returns unexpected or empty strings.  
**Cause:** Bitmask field names differ between response formats (`err` / `err_cu` / `Errors` / `NumErrors`).  
**Fix:** Enable `verbose=True` and inspect raw recv payload; confirm the error field name matches the dialect. Cross-reference against `_CU_ERROR_MESSAGES` and `_ZONE_ERROR_MESSAGES` bit positions.

### Cloud: `PolarisAuthError` at connect
**Symptom:** `PolarisCloudClient.connect()` raises `PolarisAuthError` with a login message (e.g. "wrong user or password", "terms of use / privacy not accepted").  
**Cause:** login `ResCode != 0` (table `_LOGIN_ERRORS`). Codes 6 and 10 need an action in the official app.  
**Fix:** check credentials; complete the pending step in the app. Do not retry in a loop: the account can be blocked (code 3).

### Cloud: `PolarisApiError("Wrong PIN")`
**Symptom:** `connect()` / `async_update()` raises it.  
**Cause:** `ResCode 2` (HTTP 400) from `GetCUState` or a write. The cloud never returns the PIN; it must match the one set in the app.  
**Fix:** pass the right `pin` (or `use_device(serial, pin)`).

### Cloud: `PolarisAuthError("Unauthorized (token rejected)")`
**Symptom:** raised by a read or write after a working session.  
**Cause:** HTTP 401 on the last attempt even after re-login: the rolling token counter is out of sync. Another client (the official app, a second instance) on the same login and `android_id` advances the counter too.  
**Fix:** use one `PolarisCloudClient` per account and a fixed `android_id`; reconnect.

### Cloud: write accepted but CU unchanged
**Symptom:** `update_cu` / `update_zone` return normally, `async_update()` still shows the old state.  
**Cause:** the cloud only queues the command (`ResCode 0` = queued). Firmware < 4 can take up to 10 minutes.  
**Fix:** keep polling; if the LAN is reachable use `PolarisLocalClient` with `device.ip`.

### Cloud: `TimeoutError` / warnings with no reply
**Symptom:** `get_status` raises `TimeoutError("No reply from cloud ...")`, or writes log "No response for upd_*".  
**Cause:** network error, HTTP timeout or a non-JSON reply on every attempt.  
**Fix:** check internet access to `proair.azurewebsites.net`; enable `verbose=True` to see each request.

## Debugging Checklist
1. Enable `verbose=True` on `PolarisLocalClient` — all TCP send/receive payloads log to `DEBUG`
2. Confirm `await client.connect()` (or `async with`) completed before issuing commands
3. Verify `_connected=True` via `client.connected` property
4. Inspect raw status payload to confirm field names match expected dialect (ridotto/full/cloud)
5. Test TCP connectivity manually: `nc -zv <ip> 1235`
6. Check device error state: `device.has_error` and `device.active_errors`
7. Cloud: enable `verbose=True` on `PolarisCloudClient` — every HTTP request and reply logs to `DEBUG` (login excluded). Run `examples/cloud/login.py` to isolate credential issues
8. Run the test suite to confirm no regressions: `./scripts/run_tests.sh`

## Key Code Paths
- Status fetch: `get_status()` → `_send_command_with_retry({"c":"stato_r",...})` → (res=4 fallback to `stato`) → raw dict
- Full update: `async_update()` → `get_status()` → `PolarisDevice.from_local()` + `[PolarisZone.from_local(z) for z in zones_data]`
- Zone write: `update_zone()` builds `upd_zona` cmd → `_send_command_with_retry()`
- CU write: `update_cu()` builds `upd_cu` cmd → `_send_command_with_retry()`
- Zone details: `get_zone_detail()` → `_send_command_with_retry({"c":"stato_zona",...})` → `None` raises `TimeoutError`, `res != 1` raises `PolarisApiError`; `fetch_all_zone_details()` loops non-error zones with 1 s sleep, skips failures, merges `shu`/`fan` into each `PolarisZone`
- Cloud read: `PolarisCloudClient.async_update()` (inherited) → `get_status()` → `_device_call("GET", "/api/v1/GetCUState")` → zone `Temp`/`SetTemp` /10 → shared `from_local()`
- Cloud write: inherited `update_cu()` / `update_zone()` → overridden `_send_command_with_retry()` → `UpdateCUData` / `UpdateZonaData` with the command in `Cmd`
- Cloud transport: `_device_call()` (lock, re-login when `SESSION_TTL` passed or after 401, bump token) → `_request()` → `(status, json)`; `(0, None)` on network error
- Transport: `_send_command_with_retry()` → retries → `asyncio.wait_for(_send_and_receive(), timeout)` → open TCP → write JSON → read response → close socket

## Exception Classes
- `TimeoutError` (stdlib) — no response after all retries (`connect`, `async_update`, `get_status`, `get_zone_detail`)
- `PolarisApiError` — device replied with an error; today only `get_zone_detail` on `res != 1`
- `ValueError` — invalid arguments (e.g., missing `set_temp`, invalid subnet)
- `PolarisAuthError` (cloud, subclass of `PolarisApiError`) — login rejected, or token refused after re-login
- `PolarisApiError` (cloud) — wrong PIN (`ResCode 2`), other non-zero `ResCode`, a command with no cloud endpoint, `get_zone_detail` (local-only)
- `OSError` / `ConnectionError` from a refused or reset TCP connection are caught inside `_send_command_with_retry` and retried; they surface as `TimeoutError` (or `None` for write commands)
