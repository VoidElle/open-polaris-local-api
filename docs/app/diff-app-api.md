# Report: Tecnosystemi app (Polaris CU) vs `open_polaris_local_api`

Date: 2026-11-02. Compares the flows in [local-flows/](local-flows/README.md) and [http-flows/](http-flows/README.md) (source: app) with the library (`open_polaris_local_api/`, `README.md`, `examples/`, `tests/`).

Paths: app = `open-pico-local-api/Export-Pico/sources/it/tecnosystemi/TS`, `res/...` = `Export-Pico/resources/res/...`; lib = repo root.

Method: 3 comparison agents (transport/discovery/provisioning, runtime/parsing/crono, cloud/firmware/lib-docs) + 3 adversarial verifiers, one per area. 39 raw findings: 29 confirmed, 10 partial (corrections from the verifier integrated), 0 refuted. Duplicates across areas merged into 25 items below. Library behavior was proven with `python3 -I -c` runs where noted.

> **Latent vs live.** The library has no cloud client (#7). Every finding about cloud PascalCase keys (#8, #9, #22, #23) only bites if a caller feeds a cloud payload to the models. Local findings are live.
>
> **Source caveat.** `Commands/MySocket.doInBackground` is scrambled, and `receiveDataFromSocket` (`MySocket.java:215-239`) swallows read exceptions. App retry facts (#11) are intent-level.

## Summary

| # | Sev. | Type | Title |
|---|------|------|-------|
| 1 | medium | parsing | `res` not checked on status polls and writes: wrong PIN / CU error reported as success (`stato_zona` is checked) |
| 2 | medium | parsing | `_parse_temp` heuristic: temps under 10.0 °C not scaled (local and cloud); humidity >= 100 wrongly divided |
| 3 | medium | parsing | `co` in `stato_r` zones used as temperature fallback; app: boolean `coff` flag |
| 4 | medium | discovery | Discovery requires `serial` + `fw_ver`; app local replies use `ser`, Polaris parsers read neither; README says `res=4` is enough |
| 5 | medium | wire | `upd_cu`: absent `f_inv`/`f_est` sent as 0 (app -1); `cool_mod` forced 0 when heating; `t_can:0` before first poll |
| 6 | medium | gap | No crono (`get_fasce`/`upd_fasce`) and no clock (`upd_date`) |
| 7 | medium | gap | Library is TCP only, no cloud client and no LAN-then-cloud fallback |
| 8 | medium | parsing | Cloud CU `Errors` bitmask ignored; `NumErrors` (a count) decoded as bitmask (latent) |
| 9 | low | parsing | Cloud zone `IsMaster` read as `isMaster` (latent) |
| 10 | low | wire | Request JSON has spaces and `\u` escapes; app sends compact raw UTF-8 |
| 11 | low | wire | Retry/timeout model differs |
| 13 | low | robustness | First short read treated as full reply |
| 14 | low | robustness | PIN not validated; int PIN sent as JSON number |
| 15 | low | discovery | Probe needs the real PIN and sends it in clear to every host; app probes with `check_pin("")` |
| 16 | low | gap | No `check_pin`, `scan_wifi`, `config` (no provisioning, no PIN validation) |
| 17 | low | robustness | No write/poll serialization |
| 18 | low | wire | `upd_zona`: keys omitted when set-point unknown; fancoil wins over serranda; rounding differs only off 0.1 steps |
| 19 | low | parsing | Error texts for bits 5-7 invented; app: "System status not synchronized" |
| 20 | low | parsing | Zone booleans: app `== 1`, lib `!= 0` |
| 21 | low | lib-doc | `set_zone_serranda` docstring "0=Auto"; app 0=closed, 7=Auto (wire 16) |
| 22 | low | parsing | Cloud zone fields: `IsCronoActive`, `COff` not parsed; `EV` default 0 (app -1); `isCooling` key does not exist; `Name` casing (latent) |
| 23 | low | parsing | Cloud `ResCode` not handled: error body parsed as default state (latent) |
| 24 | low | gap | No firmware catalog / OTA / version gating; README silent |
| 25 | info | semantics | `fetch_all_zone_details` fan-out (unused by the lib) |

## 1. `res` never checked: medium

- **App**: missing `res` -> null (`Commands/MySocket.java:359-372`); setters act only on `res == 1` (`Activity/ControlUnitActivity.java:332,720,754,868,898`); poll with `res != 1` -> null -> synthesized error bit 5 (`Activity/BaseActivity.java:1429-1480`); `res == 4` on `stato_r` -> fallback to `stato` (`:1404-1417`). Toast on `res != 1` only when the caller passes `z=true` (`MySocket.java:~338-345`).
- **Lib**: returns any JSON dict (`client.py:373-442`); only `res == 4` inspected on status polls (`:129`); write commands ignore `res`.
- **`stato_zona` is checked**: `get_zone_detail` raises `PolarisApiError` when `res != 1`, missing `res` included (`client.py:316-319`), so `fetch_all_zone_details` skips the zone instead of resetting fancoil/serranda to -1 (`:342-345`).
- **Impact**: wrong PIN or CU error looks like success; entities show default state.

## 2. `_parse_temp` heuristic: medium (verifier: broader than first reported)

- **App**: local `t`/`t_set` are int tenths, always `/10.0` (`Model/Zona.java:487,490,568,571`); cloud also `/10` (`:455-459`). Humidity `u`/`u_set` kept as raw strings, never scaled (`:520,523,598,601`).
- **Lib**: divides only if `abs(v) >= 100` (`models.py:40-53`), and humidity goes through the same function (`:158,160`). Proven: `t=95 -> 95.0`, `t=-50 -> -50.0`, `u=120 -> 12.0`.
- **Impact**: any temperature under 10.0 °C (frost protection, outdoor, negative) is 10x wrong; humidity >= 100 divided.

## 3. `co` used as temperature: medium

- **App**: ridotto zone parser reads temp from `t` (`Zona.java:568`) and `co` as the `coff` flag (`:615-620`, `Utils/Constants.java:138`); `setCoff()` also derives it (`Zona.java:339`).
- **Lib**: `models.py:138` falls back to `co` for current temp; no `coff` field. Proven: `from_local({'co':1}).current_temp == 1.0`.
- **Impact**: when `t` is absent, 0/1 shown as temperature; zone-off flag lost.

## 4. Discovery keys: medium (partial)

- **App**: every local-reply serial is `ser` (`Constants.JSON_SER`, `Utils/Constants.java:186`; `Activity/Config/ConfigActivity.java:127,182`). `fw_ver` appears only in PICO/SeiX replies (`CheckLedPICOActivity.java:111`, `PicoActivity.java:198`). Polaris local parsers (`Model/ControlUnit.java:455-600`) read no serial, name, fw or ip.
- **Lib**: requires `fw_ver` and `serial` and `res` in (1, 4) (`polaris_auto_discovery.py:25-34`); models read them with blank defaults (`models.py:240-243`). README (Auto-Discovery notes) states that a `res=4` reply also needs `fw_ver` and `serial`; tests inject `fw_ver`/`serial` into the `res=4` case (`tests/test_polaris_auto_discovery.py:46-49`).
- **Impact**: if Polaris `stato_r` carries `ser` (or nothing), discovery finds no device and identity is blank. Needs a device capture. Fix if confirmed: accept `ser`, or drop the key requirement.

## 5. `upd_cu` payload: medium

- **App**: parsers default `f_inv`/`f_est` to -1 in local and cloud paths (`ControlUnit.java:489-505,566-582,645-672`); -1 hides the feature (`ControlUnitActivity.java:44,628-640`) and is echoed back in `upd_cu` (`ControlUnit.java:317-336`). `cool_mod` stored only when the key is present (`:472-473,549-550,624-625`) and echoed raw.
- **Lib**: absent `f_inv`/`f_est` -> 0 (`models.py:253-256`), sent as 0 (`client.py:266-267`); `operating_mode` forced 0 when not cooling (`models.py:232-237`), sent as `cool_mod` (`client.py:264`); `_device is None` -> `t_can:0`. Proven: `from_local({'cool_mod':2,'is_cool':0}).operating_mode == 0`, `from_local({}).f_inv == 0`.
- **Impact**: writes 0 where the app writes -1; heating toggle may overwrite the remembered cooling sub-mode (CU effect unverified, inferred).

## 6. No crono, no clock: medium

- **App**: `get_fasce`, `upd_fasce`, `upd_date` (`Commands/Protocols.java:7,15,16`); 7 days x 4 slots, void slot `t=240` (`Model/Crono.java:89-94`); `upd_date` d/h/m (`ControlUnitActivity.java:306-355`). Cloud: `GetTW`/`UpdateTW`.
- **Lib**: none; only `is_crono_mode`.
- **Impact**: schedules and CU clock cannot be read or written.

## 7. No cloud client: medium

- **App**: LAN first at the cloud `IP`, then cloud with `?create_command=false` (`ControlUnitActivity.java:782,925`, `ZoneActivity.java:532`, `CronoSetActivity.java:465`); cloud poll `GET /api/v1/GetCUState` (`res/values/strings.xml:830`).
- **Lib**: TCP only (`client.py`). The README states that only cloud-shaped *parsing* exists.
- **Impact**: no remote access and no fallback when the LAN path fails.

## 8. Cloud CU `Errors`: medium, latent (partial)

- **App**: `GetCUState` path reads `Errors` as bitmask (`ControlUnit.java:606,636`, `Utils/Functions.java:601`); `NumErrors` is a plain count in the legacy `GetHome` path (`ControlUnit.java:427-428`).
- **Lib**: CU reads `err_cu` / `NumErrors` / `num_errors` only (`models.py:258-259`); `Errors` ignored for CU. Fixture `tests/test_models.py:312`. Proven: `{'NumErrors':3,'Errors':5}` -> `num_errors=3`.
- **Impact**: cloud CU errors lost; a `NumErrors` count would be decoded as a bitmask.

## 9. Cloud zone `IsMaster`: low, latent

- **App**: `@SerializedName("IsMaster")` (`Zona.java:70-72`).
- **Lib**: `data.get("isMaster")` (`models.py:154-156`); fixture `tests/test_models.py:187` uses the same wrong case. Proven: `from_local({'IsMaster':True}).is_master == False`.

## 10. Request framing: low

- **App**: compact org.json, raw UTF-8, no terminator (`ControlUnit.java:317-336`, `MySocket.java:206-213`). Gson-built commands (`check_pin`, `scan_wifi`) escape `<>&='` as `\uXXXX`; only `configCu` disables HTML escaping (`MySocket.java:~277`).
- **Lib**: `json.dumps` default separators, `ensure_ascii=True` (`client.py:408`, `polaris_auto_discovery.py:22`). Proven: `{"c": "upd_zona", "pin": 1234, "n": "Cucina è"}`.
- **Impact**: risk only if the CU parser is naive; unverified.

## 11. Retry/timeout: low

- **App**: connect 1000 ms x2 with 800 ms sleep; soTimeout 1000 ms, 15000 ms for long commands (`MySocket.java:161-191`, `Utils/Constants.java:26`); outer 3 tries, 500 ms (`MySocket.java:334-345`).
- **Lib**: 5.0 s `wait_for`, 2 total attempts, 1.0 s delay (`client.py:36-38,373-396`), ~11 s worst case. Also retries refusals and decode errors, so a refused connection surfaces as `TimeoutError` (`OSError` caught at `client.py:397`).

## 13. Short read: low (inferred)

- **App**: 1000 B chunks, stops when a read returns < 1000 (`MySocket.java:215-239`). **Lib**: `read(4096)`, breaks on `len(chunk) < 4096` (`client.py:413-421`). Same heuristic; risk of truncated JSON if a reply spans segments. Needs a capture.

## 14. PIN type: low

- **App**: 4-digit string (`Activity/Config/SetNameAndPinActivity.java:266-289`, `Cmd.java:16`). **Lib**: type hint only (`client.py:33,403`); an int PIN is sent as a JSON number and loses leading zeros.

## 15. Discovery probe and PIN: low

- **App**: liveness = `check_pin("")`, any non-empty reply = alive (`BaseActivity.java:1634-1639`); `check_pin` returns `res==1` only for a valid PIN (`SetNameAndPinActivity.java:213-250`).
- **Lib**: probes with `stato_r` and the user PIN (`polaris_auto_discovery.py:18-22`), sent in clear to every host on port 1235 of the subnet.
- **Impact**: wrong PIN likely means "not found" (what a wrong-PIN `stato_r` reply contains is unknown); PIN leaks to any listener on 1235.

## 16. No provisioning commands: low

- **App**: `check_pin`, `scan_wifi`, `config` (`MySocket.java:253-314`). **Lib**: only `stato_r`, `stato`, `stato_zona`, `upd_zona`, `upd_cu`. `check_pin` would be the useful one, for config-flow PIN validation.

## 17. No write/poll serialization: low (partial)

- **App**: poll gate `!gettingstate && !interrupt && !sendingstate` (`BaseActivity.java:1315`), but an unsynchronised boolean with separate poll threads (`:1340-1362`), so best-effort only.
- **Lib**: no lock. Concurrent poll + write connections possible; CU tolerance unknown. Fix: per-client `asyncio.Lock`.

## 18. `upd_zona`: low (partial)

- **App**: always sends both `fan_set` and `shu_set`, serranda 7 -> 16; `t_set = (int)(x*10)` (`Zona.java:359-387`).
- **Lib**: keys omitted when the set-point is -1; fancoil wins when both present (`client.py:206-228`); `round(x*10)`.
- Verifier correction: for every 0.1 step 10.0..34.9, `int(x*10) == round(x*10)` in IEEE double, so rounding differs only for non-0.1 inputs (20.55 -> app 205, lib 206).

## 19. Error texts: low (partial)

- **App**: `res/values/arrays.xml:27-36` (`cu_errors`), `:37-46` (`zone_errors`). Bits 1-4 match the library. Bits 5-7 are all "System status not synchronized, please try again later". Bit 5 is client-injected when the poll returns null (`ControlUnitActivity.java:610-620`, online CUs only; `ZoneActivity.java:795` unconditional).
- **Lib**: `models.py:11-35` invents "E6 - Server Error", "E7 - Server Error", "Network error...", "Error: status request".

## 20. Zone booleans: low (partial)

- **App**: zone off/crono strictly `== 1` (`Zona.java:481,511,562,592`). CU uses `== 0` -> false else true (`ControlUnit.java:458-469,535-546`), same as the lib.
- **Lib**: `_parse_bool` `!= 0` (`models.py:56-66`). Differs only for zone values other than 0/1.

## 21. Serranda docstring: low

- **App**: 0 closed, 1-3 A1-A3, 4-6 Auto1-3, 7 Auto, sent as 16 (`Utils/Constants.java:294-312`). **Lib**: `client.py:361-367` "0=Auto". Callers passing 0 close the shutter.

## 22. Cloud zone fields: low, latent

- `IsCronoActive` (`Zona.java:62`), `COff` (`:94`) not parsed; `ManCrono` derived from `IsCronoMode` (`:444-446`), lib `man_crono` always 0 from cloud.
- `EV` default -1 (`Zona.java:90-92`); lib 0 (`models.py:99,147`), so absent reads as closed.
- Zone `isCooling` key does not exist (cooling is CU `IsCooling`); lib reads it (`models.py:~148`), always False.
- App uppercases CU names (`ControlUnit.java:613`); lib keeps them. Cosmetic.

## 23. Cloud `ResCode`: low, latent (inferred)

- **App**: `ResCode` 0/absent = body used; 2 with type 12 = wrong PIN (`Threads/ThreadWebService.java:1095-1102`). **Lib**: an error body parses as defaults ("Unknown", zeros).

## 24. Firmware: low (partial)

- **App**: catalog `GET /api/v4/FWs`, download `GET /api/v1/FW` (`res/values/strings.xml:826,848`), AP `POLARIS_UPDATE` bootloader (`Utils/Constants.java:273`), major-version gating (`Utils/Functions.java:387`, `ControlUnitActivity.java:1201`). See [local-flows/05-firmware-ota.md](local-flows/05-firmware-ota.md).
- **Lib**: raw `fw_ver` string from discovery only (`polaris_auto_discovery.py:29,128`); no firmware features; README silent.
- Verifier correction: the claim "`fw_ver` empty from `stato_r`" was refuted. `v` in the `client.py:~309` docstring is the per-zone firmware from `stato_zona`. Expected scope gap; README should state it.

## 25. `fetch_all_zone_details`: info (partial)

- **App**: polls `stato_zona` for the one zone shown, every 5 s (`BaseActivity.java:162,1338-1362`).
- **Lib**: public helper, never called by the library (`async_update` uses only `get_status`, `client.py:139-162`); queries every non-error zone with a 1 s sleep each (`:330-339`). Only matters if a caller (the HA integration) opts in.

## Suggested priorities

1. #1 `res` handling and #2 temperature scaling: live, user-visible, small fixes in `client.py` / `models.py`.
2. #3 `co`, #5 `f_inv`/`f_est` -1 sentinel and `cool_mod` echo: wrong data read or written.
3. #4 discovery keys: confirm with a capture, then accept `ser`.
4. Docs: #21 (`set_zone_serranda` docstring).
5. Cloud-key fixes #8, #9, #22 only if a cloud client is added.
6. Features: #6 crono/clock, #16 `check_pin`.

## Questions for hardware tests

- Does Polaris `stato_r` carry `serial`/`ser`, `fw_ver`, `name`? (#4)
- What does `stato_r` with a wrong PIN return? Meaning of `res` other than 1 and 4? (#1, #15)
- Does the CU accept JSON with spaces and `\u` escapes in zone names? (#10)
- Does `upd_cu` with `f_inv:0` instead of -1, or `cool_mod:0` while heating, change CU state? (#5)
- Does `upd_zona` without `fan_set`/`shu_set` keep the current values? (#18)
- Do `stato` replies ever span more than one TCP segment? (#13)
- Does the CU tolerate a poll and a write on two concurrent connections? (#17)
