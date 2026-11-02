# 04 - Polaris cloud runtime

Screens: `ControlUnitActivity` (CU + zone list), `ZoneActivity` (one zone), `CronoSummaryActivity` / `CronoSetActivity` (weekly schedule). Branch point is `ControlUnit.isOffline()`: offline = TCP to `10.0.0.1:1235` ([../local-flows/README.md](../local-flows/README.md)), online = REST below. Online commands are additionally tried over LAN first (see "Hybrid delivery").

## State polling
Shared poll in `BaseActivity.inizializeGetState` (`Activity/BaseActivity.java:1305-1378`):
- `Handler.postDelayed(..., thread_sleep)` with `thread_sleep = 5000` (`:162`, `:1378`). A tick is skipped while a previous request is pending (`gettingstate`) or a command is being sent (`sendingstate`) (`:1312`).
- Started in `onResume` (`ControlUnitActivity.java:1021-1031`, `ZoneActivity.java:864-872`), stopped in `onDestroy` (`stopgetState`, `BaseActivity.java:1290`). Not started in demo mode.
- URL (`ControlUnitActivity.java:66`, `:148`, `ZoneActivity.java:66`):
```
GET https://proair.azurewebsites.net/api/v1/GetCUState?cuSerial=<SER>&PIN=<PIN>
```
  `ZoneActivity` polls the same CU endpoint (zones are inside it); there is no per-zone cloud state call.
- Type 12 for the first call after entering the screen or (re)setting the PIN (`firtCalltoGetState`, init `BaseActivity.java:200`, reset `ControlUnitActivity.java:151`), type 11 afterwards (`:1324-1327`). Only type 12 reacts to `ResCode 2` with the PIN dialog (`ThreadWebService.java:1097-1115`); a wrong PIN on type 11 just yields no data.
- No data (network error, non-200, `ResCode != 0`, parse error) -> `getCuState(null)` injects CU error bit 5 (`Functions.geterror(32)`, `NumError = 1`) and the zone screen does the same (`ControlUnitActivity.java:615-626`, `ZoneActivity.java:765-772`). UI text for bits 5-7: "System status not synchronized, please try again later" (`res/values/arrays.xml:33-35`, `:43-45`).
- On success: `ControlUnit.getCuFromJSONFromServer` + `mergeFromGetState` overwrite on/off, cooling, zones, errors, T_can, IR, F_inv/F_est, FW, name, `LastSyncUpdate`, and `IP` when present (`ControlUnitActivity.java:643-650`; `Model/ControlUnit.java:606-711`). Non-null `IP` also initialises the local socket (`:643-645`).

### `GetCUState` reply (flat JSON, PascalCase; keys read at `Model/ControlUnit.java:606-688`)
| Key | Type / decode | Notes |
|-----|---------------|-------|
| `Serial`, `Name` (upper-cased), `FWVer` | string | `Name` also overwrites the local name |
| `IsOFF` | bool | CU off |
| `IsCooling` | bool | heating vs cooling |
| `OperatingModeCooling` | int | `cool_mod` value; library names 0-3 (`models.py:226`) |
| `TempCan` | int tenths C | `/10` (`:643-649`); sent back as `t_can*10` |
| `FInv`, `FEst` | int | winter/summer functions; missing or non-int -> `-1` = feature hidden (`hasfinest`) |
| `IrPresent` | int | |
| `Errors` | int bitmask | LSB-first, 8 bits (`Functions.geterror`, `Utils/Functions.java:601-612`); CU labels `res/values/arrays.xml:27-36` |
| `IP` | string | CU LAN IP, enables hybrid delivery |
| `LastConfigUpdate`, `LastSyncUpdate` | string | shown only in developer mode (`Constants.modesviluppatore`, `Utils/Constants.java:317`) |
| `Icon` | int | |
| `Zones[]` | array | below |

`ResCode` is absent on success. If present and non-zero the body is discarded (`ThreadWebService.java:1097-1100`).

### Zone object (`Model/Zona.java:17-98`, Gson `@SerializedName`)
| Key | Type | Decode / meaning |
|-----|------|------------------|
| `ZoneId` | int | |
| `Name` | string | |
| `Temp`, `SetTemp` | string tenths | `parseDouble / 10` -> C (`getZonaFromJson :456-459`) |
| `Umd`, `SetUmd` | string | humidity / set humidity (not scaled) |
| `IsOFF` | bool | |
| `Fancoil`, `FancoilSet` | int | `-1` = no fancoil; `7` in the app UI = auto (sent as 16) |
| `Serranda`, `SerrandaSet` | int | damper; `-1` = none |
| `EV` | int | valve state (`-1` default) |
| `IsCronoMode` | bool | zone follows schedule (`ManCrono` derived: 1/0) |
| `IsCronoActive` | bool | a schedule slot is currently active (`fasciaAttiva`) |
| `IsMaster` | bool | |
| `Errors` | int bitmask | 8 bits, `res/values/arrays.xml:37-46` |
| `CBadge`, `CWin` | object | badge / window contact (opaque, `Object`) |
| `COff` | bool | |
Library overlap: see README "Library coverage". `Errors` bit labels in the app: bit0 "E0 - No communication", 1 "E2 chrono-actuator association", 2 "E3 actuator failure", 3 "E4 actuator communication error", 4 "E5 low battery", 5-7 "status not synchronized".

## Hybrid delivery (LAN first, then cloud)
Commands for an online CU follow the same pattern (`ControlUnitActivity.saveData :743-766`, `saveData(int) :889-925`, `ZoneActivity :493-532`, `CronoSetActivity :435-470`, date `:328-344`):
1. If the CU `IP` (from `GetCUState`) is known: send the command JSON over TCP to `<IP>:1235` with the **online** PIN. Reply `{"res":1}` = delivered; `res` present and `!= 1` = toast `msg_commandKo` and stop; no/empty reply = continue.
2. POST the cloud endpoint. If step 1 returned `res:1` the URL gets `?create_command=false` (cloud told not to queue a CU command; inferred) and the OK toast is immediate (`params[0] = "0"`, `Constants.COMMANDSENT`). Otherwise `params[0] = "1"` (`COMMAND10MIN`): toast "applied within 10 minutes" for FW major < 4, plain OK for FW >= 4 (`ThreadWebService.updState :1170-1181`, `Functions.IS4x :387`).
3. Name-only edits set `params[0] = "2"` (`ONLYNAME`) and send `Cmd:""` (`ControlUnitActivity.java:703-706`, `:788-790`).
Unlike PICO there is no `frm`/`idp` envelope and no per-command ack from the CU; the next poll shows the result. While a send is pending, polls are skipped (`sendingstate`). On a failed zone send `ZoneActivity.resetTemp()` reverts the UI (`ThreadWebService.java:1135-1233`).

## Write endpoints
All POST, `Authorization`/`Token` as in [01](01-http-transport-auth.md), reply `{ResCode, ResDescr}` (0 ok, 2 wrong PIN -> `pinerror`, else `msg_commandKo`; 400 same body). `Cmd` is the **local-protocol JSON serialised into a string** (double-encoded). Note the key capitalisation differs between endpoints.

| Endpoint | Body | `Cmd`/`cmd` content |
|----------|------|---------------------|
| `/api/v1/UpdateCUData[?create_command=false]` | `{"Serial","Name","Pin","Cmd"}` (`ControlUnitActivity.java:774-777`) | `{"c":"upd_cu","pin":"<PIN>","is_off":0\|1,"is_cool":0\|1,"cool_mod":n,"t_can":<C*10>,"f_inv":n,"f_est":n}` (`Model/ControlUnit.java:317-336`) |
| `/api/v1/UpdateZonaData[?create_command=false]` | `{"Serial","Name","Pin","ZoneId","Cmd"}` (`ZoneActivity.java:524-527`, `ControlUnitActivity.java:917-920`) | `{"c":"upd_zona","id_zona":n,"name":"..","is_off":0\|1,"t_set":"<C*10 int as string>","fan_set":n,"shu_set":n,"is_crono":0\|1,"pin":"<PIN>"}` (`Zona.update_ZONA_Command :353-388`). `fan_set`/`shu_set` both set from whichever of fancoil/damper exists; UI value 7 -> 16 |
| `/api/v1/UpdateCUDatetime` | `{"Serial","Name","Pin","cmd"}` (`ControlUnitActivity.java:347-354`) | `{"c":"upd_date","pin":"..","h24":n,"d":n,"h":n,"m":n}` (`Protocols.java:16`) |
| `/api/v1/UpdateTW[?create_command=false]` | `{"Serial","ZoneId","Pin","cmd"}` (`CronoSetActivity.java:457-460`) | `{"c":"upd_fasce","id_zona":n,"pin":"..","0":[slot x4],...,"6":[slot x4]}`, slot `{"i":start15,"f":end15,"t":<C*10>}`, empty slot `{"i":0,"f":0,"t":240}` (`Zona.updCronoCommand :413-436`, `Crono.java:63-90`) |

Handlers: `updState :1126` (13), `updTW :1331` (15), `updCUDatetime :1398` (16). Key casing: `Cmd` (UpdateCUData/UpdateZonaData) vs `cmd` (UpdateCUDatetime/UpdateTW); `Pin`/`Serial`/`Name` PascalCase in the envelope, `pin` lower-case inside the inner command. The inner JSON is exactly the local TCP command (library `update_cu`/`update_zone`, `client.py:167-282`, produce the same bodies).

## Schedules (crono)
- Read: `GET /api/v1/GetTW?cuSerial=<SER>&zoneID=<ZONE>&PIN=<PIN>` (type 14, `CronoSummaryActivity.java:118`, handler `getTW :1259`). Reply: object keyed by Italian day abbreviations `Lun,Mar,Mer,Gio,Ven,Sab,Dom` (`Constants.java:329`), each an array of slots `{"Type":0-3,"Start":n,"End":n,"Temp":n}` (`CronoSummaryActivity.getTW :146-171`; `Crono` fields `Start/End/Temp`, `Model/Crono.java:12-17`).
- Decode (`Crono.normalizzaOrario :19-45`): `Start`/`End` = quarter-hour index (`*15` min -> `HH:MM`), `Temp` tenths of C; `Start=End="0"` = empty slot. 4 slots/day (F1..F4), 7 days.
- Write: `UpdateTW` (above). Validity (`Crono.isok :107-122`): all three fields or none, end after start; the screen enforces filling from F1 and a SET temperature (`res/values/arrays.xml:9-26`).
- Zone schedule mode itself is `is_crono` in `UpdateZonaData` and `IsCronoMode`/`IsCronoActive` in the state.

## Restore
`GET /api/v1/SendRestoreCmd?cuSerial=<SER>&PIN=<PIN>` (type 21, `ControlUnitActivity.java:1195`, handler `restConfig :526`). Menu item only if `FWVer` major >= 5 (`is5x :1201-1207`, `:1136`). `ResCode 0` -> "Command sent, wait for control unit reset" (`res/values/strings.xml:382`); 2 -> PIN error; 9 -> `cu_errorRestoreCU`. Resets the CU configuration (`strings.xml:388`).

## What does not exist online
- No `stato_sync`/`lastpk`/`frm:"mqtt"` layer: those belong to PICO/VMC/6X (`Protocols.CMD_STATOSYNC` is used only by `VMCActivity.java:161`, `SeiXMainActivity.java:125`).
- `ResetConnection` (`GET /api/v1/ResetConnection`, type 19, `ControlUnitActivity.resetConn :1007`) is unreachable: the menu `Runnable` is constructed and discarded (`:1171-1177`).
- No push of state: FCM carries alerts only ([05](05-firmware-push.md)). No retry/backoff beyond the next 5 s tick.

## Sequence (zone setpoint change)
```
tap -> tempZona.update_ZONA_Command()                       [sendingstate=true, poll paused]
 -> (if IP known) TCP <IP>:1235 {"c":"upd_zona",...}  <- {"res":1}
 -> POST /api/v1/UpdateZonaData[?create_command=false] {Serial,Name,Pin,ZoneId,Cmd:"{..}"}
 <- 200 {"ResCode":0}                                        [toast, sendingstate=false]
 -> (<=5 s) GET /api/v1/GetCUState?cuSerial=&PIN= <- {IsOFF,..,Zones:[{ZoneId,Temp,SetTemp,..}]}
```
