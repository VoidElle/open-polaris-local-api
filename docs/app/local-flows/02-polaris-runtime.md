# POLARIS runtime: state polling and commands (CU + zones)

Paths relative to `.../Export-Pico/sources/it/tecnosystemi/TS`. Transport details in `01-transport.md`. Crono (`get_fasce`/`upd_fasce`) in `03-crono.md`.

## 1. State polling

`BaseActivity.inizializeGetState(boolean local)` (`Activity/BaseActivity.java:1305-1381`): a `Handler.postDelayed` loop every `thread_sleep = 5000` ms (`:162,1378`). A tick is skipped if `gettingstate || interrupt || sendingstate` (`:1315`), so polling pauses while a write is in flight.

| Activity | `local == true` (offline CU, AP mode) | `local == false` (online CU) |
|---|---|---|
| `ControlUnitActivity` | TCP `{"c":"stato_r","pin":<PinOffline>}` to `10.0.0.1:1235` (`BaseActivity.java:1340-1346`) | cloud `GetState` HTTP (`:1318-1329`, out of scope) |
| `ZoneActivity` | TCP `{"c":"stato_zona","pin":..,"id_zona":<zoneId>}` (`:1353-1361`) | cloud |

- `local` = `cu.isOffline()` (`ControlUnitActivity.java:1031`, `ZoneActivity.java:870`). The app never polls TCP on the LAN IP.
- `stato_r` ("ridotto", compact keys) is tried first. If the reply has `res == 4` the app re-sends `{"c":"stato","pin":..}` (full keys) (`BaseActivity.java:1404-1417`). Next tick starts with `stato_r` again (no caching of the fallback decision).
- Reply handling: `res != 1`, empty or unparsable -> `null` state (`offlineResCU` `:1429-1455`, `offlineResZona` `:1457-1480`). Offline CU with `null` -> UI keeps old data (`ControlUnitActivity.java:614-616`); online CU -> sets error bit 5 (`Functions.geterror(32)`, `:618`); zone with `null` -> error bit 5 (`ZoneActivity.java:795`).
- Merge: `ControlUnit.mergeFromGetState` overwrites `isOff, isCooling, master, zone[], operatingMode, errors, numError, t_can, ir_present, f_inv, f_est` (`Model/ControlUnit.java:690-706`).
- `res == 4` check is only done on `stato_r`; `stato` / `stato_zona` replies with other codes are dropped.

## 2. CU state parsing

Dispatch (`Model/ControlUnit.java:529-534`): if reply has `c == "stato_r"` -> ridotto parser (`:455-527`), else full parser (`:529-...`).

| Field | Full (`stato`) | Ridotto (`stato_r`) | Semantics |
|---|---|---|---|
| CU off | `is_off` (0 = on, else off) | `off` | `Constants.java:160,162` |
| Cooling | `is_cool` | `cl` | 0 = heating, else cooling |
| Operating mode | `cool_mod` | `cl_m` | 1 raff, 2 umd (dehum), 3 vent (`Constants.java:34-36`) |
| CU errors | `err_cu` | `err_cu` | 8-bit mask, `Functions.geterror` LSB first (`Utils/Functions.java:601-612`); `numError` = count of set bits |
| Master nr | `master_nr` | `m_nr` | `setMaster(int)` |
| IR present | `ir_present` | `ir` | |
| Canal temp | `t_can` / 10 (int div) | `tc` / 10 | unit 0.1 C; absent -> `t_can` 0 on parse failure |
| F est / F inv | `f_est`, `f_inv` | `fe`, `fi` | absent -> `-1` (feature not present; drives menu `hasfinest`, `ControlUnitActivity.java:632-637`) |
| Zones | `zone[]` | `zone[]` | key `zone` in both (`Constants.java:183`) |

The app does NOT read `serial`, `name`, `fw_ver`, `ip` from local replies (nothing in `ControlUnit.java:455-640` touches them). Serial/name/FW come from the cloud or prefs (inferred: whether the CU sends them is unknown).

## 3. Zone state parsing

Full: `Zona.getZonaFromJsonOffline` (`Model/Zona.java:469-548`). Ridotto: `getZonaFromJsonOfflineRidotto` (`:550-636`). Same parser is used for `stato_zona` replies (`ZoneActivity.getZoneState`, `:792-818`).

| Field | Full key | Ridotto key | Notes |
|---|---|---|---|
| zone id | `id_zona` or `nr` | `id_zona` or `nr` | both accepted in both parsers (`Zona.java:473-478,554-559`) |
| zone off | `is_off` == 1 | `off` == 1 | strictly `== 1` |
| name | `name` | `n` | |
| temp | `t` / 10.0 | `t` / 10.0 | double string |
| set temp | `t_set` / 10.0 | `ts` / 10.0 | |
| fancoil / set | `fan`, `fan_set` | same | -1 = absent; 0 closed, 1..3 A1..A3, 4..6 Auto1..3, 7 Auto (`Constants.java:294-302`) |
| serranda / set | `shu`, `shu_set` | same | same enum (`:304-312`) |
| EV | `EV` | `EV` | |
| zone err | `err` | `err` | 8-bit mask; zone messages from `R.array.zone_errors` |
| crono mode | `is_crono` == 1 | `is_crono` == 1 | |
| slot active | `crono_on` == 1 | `crono_on` == 1 | `setFasciaAttiva` |
| humidity / set | `u`, `u_set` (strings) | `u`, `us` | |
| window / badge | `c_win`, `c_badge` | `w`, `b` | ints |
| coff | - | `co` == 1 | `setCoff(boolean)`; NOT a temperature (`Zona.java:615-621`) |
| CU off (zone state only) | `is_off_cu` == 1 | - | `ZoneActivity.java:804-808` |

`ManCrono` is set from `isCronoMode` for cloud JSON only (`Zona.java:438-448`).

## 4. Commands

All sent with `MySocket.commandToCU` (see 01). Success = `res == 1` -> toast `msg_commandOk`; otherwise `msg_commandKo`.

### 4.1 `upd_cu` (`Model/ControlUnit.java:317-336`)

```json
{"c":"upd_cu","pin":"1234","is_off":0,"is_cool":1,"cool_mod":1,"t_can":220,"f_inv":0,"f_est":0}
```

- `t_can` = `getT_can() * 10` (integer degrees x10). `f_inv`/`f_est` sent raw, including `-1` when absent.
- `pin`: `PinOffline` if offline else `Pin`.
- Sender `ControlUnitActivity.saveData()` (`:698-790`). Skipped entirely when only the name changed (`onlyname()`, `:~815`: compares `isOff, isCooling, operatingMode, t_can, f_est, f_inv`).
- Offline: TCP to `10.0.0.1`; online: TCP to `cu.getIp()` then cloud (`:747`, `:~760-790`).
- Clamp: canal temp UI range C `tempminC..tempmaxC` 10..35, F 50..95, canal F 64..86 (`Utils/Constants.java:412-417`; used `ControlUnitActivity.java:560-561`).

### 4.2 `upd_zona` (`Model/Zona.java:353-396`)

```json
{"c":"upd_zona","id_zona":1,"name":"Salotto","is_off":0,"t_set":"215","fan_set":16,"shu_set":16,"is_crono":0,"pin":"1234"}
```

- `t_set` = `String.valueOf((int)(Double.parseDouble(setTemp) * 10.0))` (truncation, string).
- `fan_set` and `shu_set` are ALWAYS both sent with the same value:
  - fancoil absent (`-1`) -> value = `serrandaSet`;
  - serranda absent -> value = `fancoilSet`;
  - both present -> `lastFancoil` flag (default true, `Zona.java:98`) selects `fancoilSet` or `serrandaSet`;
  - `7` (Auto) is sent as `16` (`Zona.java:358-390`).
- `is_crono` = 1/0. `pin` appended by the caller (`ZoneActivity.java:~456,~490`; `ControlUnitActivity.java:855-892`).
- Callers: `ZoneActivity` (`:465` offline, `:497` LAN then cloud), `ControlUnitActivity.saveData(int)` (`:863,893`).
- Sending is skipped if nothing changed (`somethingchanged()`, `ZoneActivity.java:~453`).
- Temp UI range same as CU (C 10..35, F 50..95 converted by `Functions.fromFtoC`).

### 4.3 `upd_date` (`ControlUnitActivity.java:306-355`)

```json
{"c":"upd_date","pin":"1234","h24":1,"d":3,"h":14,"m":30}
```

Fields: `h24` (24-hour flag), `d` (day), `h`, `m` from the CU object (`getH24/getDay/getOre/getMinuti`). Offline: TCP only. Online: LAN TCP first; success only if `res == 1`; otherwise clears `cu.ip` and sends via cloud (`:324-352`). Day numbering/encoding not documented in the app code read (open question).

### 4.4 Not CU-local

`stato_sync` (VMC/SeiX), PICO commands (`upd_pico`, ...): see their docs.

## 5. Error model

- CU: `err_cu` 8 bits; messages `R.array.cu_errors`. Zone: `err` 8 bits, `R.array.zone_errors`. Bit 5 (value 32) is synthesized locally on "no reply" (`ControlUnitActivity.java:618`, `ZoneActivity.java:767,795`).
- `NumErrors`/`Errors` PascalCase fields exist only in cloud JSON (`Utils/Constants.java:104,118`).

## 6. Open questions

- Whether `stato_r` replies really include `fan/shu/EV` (the ridotto parser reads them, so they are optional at least).
- Meaning of `master_nr`/`m_nr` values beyond "non-zero".
- `upd_cu` reply content (only `res` is read).
