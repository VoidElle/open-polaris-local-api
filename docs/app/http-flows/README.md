# Polaris 5X online (cloud) flows (Tecnosystemi app)

Map of the cloud flows for the Polaris 5X control unit ("ControlUnit" family in the app, `LVDV_Type 0` = `DEVICE_TYPE_PROAIR`, `Utils/Constants.java:50`) derived from `Export-Pico/sources/it/tecnosystemi/TS` (JADX, shared with the PICO analysis in the sibling `open-pico-local-api` repo).
`file:line` references are relative to that folder; `res/...` = `Export-Pico/resources/res/...`. "(inferred)" = deduced, not read.
Counterpart of [../local-flows](../local-flows/README.md) (local TCP flow).
Out of scope: PICO, VMC, SeiX (6X), local TCP, Modbus recipes.

| File | Content |
|------|---------|
| [01-http-transport-auth.md](01-http-transport-auth.md) | Base URL (`_POLARIS`), headers (Basic + rolling `Token`), `ThreadWebService` type codes used by Polaris, `ResCode` values |
| [02-account-login.md](02-account-login.md) | Login/session condensed (shared with PICO), Polaris-relevant fields of the login reply |
| [03-plants-devices.md](03-plants-devices.md) | Plant/device model for Polaris, `GetPlants`, `AddUserToDevice`, online provisioning (`AddNewCU`/`CheckConfigCU`), delete, legacy `GetHome` |
| [04-polaris-cloud-runtime.md](04-polaris-cloud-runtime.md) | `GetCUState` polling (5 s), PascalCase CU/zone fields, `UpdateCUData`/`UpdateZonaData`/`UpdateCUDatetime`, crono (`GetTW`/`UpdateTW`), errors, restore |
| [05-firmware-push.md](05-firmware-push.md) | Firmware catalog `FWs` + `FW` download (Polaris filter), FCM push |
| [06-quirks-security.md](06-quirks-security.md) | Bugs, dead code, security weaknesses, library gaps vs cloud |

Key points:
- One backend: `https://proair.azurewebsites.net` (`res/values/strings.xml:810-812`; `uriWebService`, `_PICO`, `_POLARIS` are identical). Polaris code uses `uriWebService_POLARIS` for state/commands/crono/firmware and plain `uriWebService` for account/plants (`ControlUnitActivity.java:66`, `TSDeviceListActivity.java:394`).
- App -> REST -> backend -> (inferred) CU. Backend queues commands; the CU picks them up later. UI text says changes apply "within 10 minutes" for FW < 4.x (`res/values/strings.xml:569`, `ThreadWebService.java:1175-1181`).
- Hybrid: even for a cloud-registered CU the app first tries the CU's LAN IP (reported by `GetCUState` as `IP`) over local TCP; only if that fails does it POST to the cloud (`ControlUnitActivity.java:743-766`, `ZoneActivity.java:493-512`). Cloud is then called with `?create_command=false` when TCP succeeded (record sync only, inferred).
- Local vs cloud chosen per CU by `ControlUnit.isOffline()` (`ControlUnitActivity.java:65`, `BaseActivity.java:1305-1378`).
- Auth = fixed HTTP Basic (`<email>:PwdProAir`) + rolling AES counter `Token`. Session 1 h from login, not sliding.
- State reply is a **flat PascalCase JSON** (no `ResCode`, no `ResDescr`, no `stato_sync`/`lastpk` wrapper like PICO). Command replies are `{ResCode, ResDescr}` acks only.
- Polaris REST surface is a few endpoints: `GetCUState`, `UpdateCUData`, `UpdateZonaData`, `UpdateCUDatetime`, `GetTW`, `UpdateTW`, `SendRestoreCmd`, `ResetConnection` (dead), `AddNewCU`, `CheckConfigCU`, `AddUserToDevice`, `DeleteDevice`.

## Library coverage (`open_polaris_local_api/`)
- **No cloud client.** `client.py` imports only `asyncio/json/logging` and talks TCP (`client.py:13-20`); `pyproject.toml` has no HTTP dependency. Nothing calls `proair.azurewebsites.net`.
- `models.py` already accepts cloud PascalCase as fallbacks (`models.py:3`, `:133-165`, `:226-259`), so a future cloud client could feed `GetCUState` JSON to `PolarisDevice.from_local` / `PolarisZone.from_local` (`client.py:147-155` already reads `Zones`).

| Cloud field | Library | Status |
|-------------|---------|--------|
| CU `Serial`,`Name`,`FWVer`,`IP`,`IsOFF`,`IsCooling`,`OperatingModeCooling`,`TempCan`,`FInv`,`FEst`,`IrPresent` | `PolarisDevice.from_local` (`models.py:226-258`) | understood |
| CU `Errors` (bitmask in `GetCUState`) | not read; reads `NumErrors` (`models.py:259`) which only `GetHome` sends | **gap** |
| CU `LastSyncUpdate`,`LastConfigUpdate`,`Icon`,`NumErrors` | not stored | ignored |
| Zone `ZoneId`,`Name`,`Temp`,`SetTemp`,`IsOFF`,`Fancoil`,`FancoilSet`,`Serranda`,`SerrandaSet`,`EV`,`Umd`,`SetUmd`,`IsCronoMode`,`Errors`,`CBadge`,`CWin` | `PolarisZone.from_local` (`models.py:139-165`) | understood |
| Zone `IsMaster` | read as `isMaster` (lower-case `i`) (`models.py:154-156`) | **case mismatch** |
| Zone `IsCronoActive`,`COff` | not read | ignored |
| Zone `Temp`/`SetTemp` are tenths of a degree strings | `_parse_temp` divides only if `abs(v) >= 100` (`models.py:40-52`) | wrong below 10.0 C (inferred) |
| Zone `IsCooling` | `models.py:142` reads `isCooling`; cloud zone has no such field | n/a (cooling is CU-level) |
