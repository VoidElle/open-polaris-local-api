# Report: Polaris app-docs extraction

Date: 2026-11-02. Summary of how `docs/app/` was produced, what was spot-checked, and what remains open.
Source: Tecnosystemi app (JADX export), `open-pico-local-api/Export-Pico/sources/it/tecnosystemi/TS` (paths below are relative to it; `res/...` = `Export-Pico/resources/res/...`).
In the app, Polaris is the "ControlUnit" family: `ControlUnitActivity`, `ZoneActivity`, `CronoSetActivity`, `CronoSummaryActivity`, `BootloaderActivity`, `Model/ControlUnit.java`, `Model/Zona.java`.

## Output

| Folder | Files | Lines | Content |
|--------|-------|-------|---------|
| [local-flows/](local-flows/README.md) | 7 | 524 | TCP transport, CU/zone runtime, crono, provisioning, firmware/bootloader |
| [http-flows/](http-flows/README.md) | 7 | 357 | Cloud transport/auth, account, plants/devices, CU cloud runtime, firmware/push, quirks |
| [diff-app-api.md](diff-app-api.md) | 1 | - | Verified app vs library diff scan (local + cloud) |

Method: two Sonnet agents (local, cloud), each mirroring the structure of `open-pico-local-api/docs/app/`. Navigation through the codebase-memory index; the app Java is indexed as folders only, so it was searched as text.

## Spot-checks done on the source

| Claim | Evidence |
|-------|----------|
| Local transport = TCP, AP host `10.0.0.1`, port `1235` | `Utils/Constants.java:315,319` |
| `co` in `stato_r` zones is the boolean `coff` flag, not a temperature | `Model/Zona.java:339`, `Utils/Constants.java:138` |
| Cloud endpoints come from string resources | `res/values/strings.xml:830` (`/api/v1/GetCUState`), `:846` (`/api/v1/UpdateZonaData`) |
| LAN-first write, then cloud with `?create_command=false` | `ControlUnitActivity.java:782,925`, `ZoneActivity.java:532`, `CronoSetActivity.java:465` |
| `local-flows` and `http-flows` cross-links resolve | both `README.md` exist |

## Key protocol facts

- Local: TCP JSON on port 1235, one short socket per command, keys `c` and `pin`. `res==1` = success, `res==4` = command not found. Not the PICO UDP envelope.
- Offline CU (AP mode): `10.0.0.1:1235`, TCP polling every 5 s, `stato_r` with fallback to `stato` on `res==4`.
- Cloud CU: polling is cloud only (`GET /api/v1/GetCUState`). Writes try the LAN at the cloud `IP` field first. On `res:1` the cloud POST gets `?create_command=false`. On any other `res` the app aborts without calling the cloud.
- Cloud has no PICO-style wrapper: no `frm:"mqtt"`, `idp`, `stato_sync` or `ResDescr` state.
- Crono: `get_fasce` / `upd_fasce`, 7 days x 4 slots in 15-minute units. Cloud: `GetTW` / `UpdateTW`.
- Provisioning: AP `POLARIS_CONFIG`, then `scan_wifi`, `config`, `check_pin`. Online: `AddNewCU`, `CheckConfigCU`, `AddUserToDevice`.
- Firmware: AP `POLARIS_UPDATE`, binary `*`-framed bootloader on port 1235, S3 records, CRC16, resume. Catalog: `GET /api/v4/FWs`, `GET /api/v1/FW`.
- The library has no cloud client (`client.py` imports only `asyncio`, `json`, `logging`; no HTTP dependency).

## Library bugs found (confirmed in `open_polaris_local_api/models.py` / `client.py`)

1. `res` ignored on writes and polls: wrong PIN or CU error is reported as success.
2. `co` parsed as current temperature (`models.py:138`). It is the zone-off flag.
3. Zone master read as `isMaster` (`models.py:156`). Cloud sends `IsMaster`.
4. CU errors read from `NumErrors` (`models.py:259`). Only legacy `GetHome` sends it; `GetCUState` sends an `Errors` bitmask.
5. `_parse_temp` divides by 10 only at 100 or above. Cloud always sends tenths, so values under 10.0 °C are wrong.
6. Shutter docstring says 0=Auto. App: 0=closed, 7=Auto.

Full verified list with severities: [diff-app-api.md](diff-app-api.md).

## Open questions

- Auto-discovery needs `serial` and `fw_ver` in `stato_r`. The app never reads them locally. Needs a device capture.
- Meaning of `res` values other than 1 and 4.
- `upd_date` day encoding. `check_pin` reply with an empty PIN.
- Setup modes 1-4: labels are string resources not read; meanings in `local-flows/04-provisioning.md` are inferred.
- Does `config` with `offline:1` keep the old Wi-Fi credentials?
- `create_command=false` semantics are inferred from the name only.
- `OperatingModeCooling` values 0-3 not checked against the app.
- Polaris branch of `SelectTypeDevActivity` inferred; only the PICO branch was read.
- `MemorySize`, `WiFiVersion`: no reader found.
- `GetCUState` field list comes from app code only; not checked against a live backend.

## Caveats

- JADX reorders control flow; some line numbers are approximate.
- `local-flows/05-firmware-ota.md` skips the exact `controlloVersione` branch logic.
- `http-flows/02-account-login.md` is a condensed copy of the flow shared with PICO.
