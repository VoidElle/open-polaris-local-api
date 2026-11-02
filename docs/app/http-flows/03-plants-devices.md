# 03 - Plants and devices (Polaris)

## Model
- `Plant` ("impianto", `Model/Plant.java:15-19`): `{LVPL_Id, LVPL_Name, LVPL_Icon, LVPL_USAN_Id, ListDevices[]}`. Devices live inside a plant.
- `Device` (`Model/Device.java:15-26`), Gson field names = JSON keys: `DevId`, `LVDV_Id`, `LVDV_Type`, `Serial`, `Name`, `FWVer`, `IsOff`, `OperatingMode`, `NUM_ERROR`, `LastAddTimezone`, `LastConfigUpd`, `LastSyncUpd`. Polaris = `LVDV_Type 0` (`DEVICE_TYPE_PROAIR`; PICO 1, VMC 2, 6X 3: `Utils/Constants.java:48-51`).
- Per-CU local record `ControlUnit` (`Model/ControlUnit.java`) in prefs (`HomeUC_TS`, `Constants.java:227`): `Name, Serial, PIN, PinOffline, IsOffline, IP, UnitOfMeasure, h24, Icon, FInv, FEst` (`cuLocalJson :297-310`). **The PIN lives on the phone** and goes out with every device call (query string or body).
- `isOffline` is a property of the phone's record, not of the server device.

## List plants
`GET /api/v1/GetPlants` (type 23; `TSHomeActivity.java:177`, `TSDeviceListActivity.java:394`). Handler `getHomeTS` (`ThreadWebService.java:282`): `ResCode 0` -> `ResDescr` is a JSON **string** holding `ArrayList<Plant>` (double-encoded). Same list arrives at login as `ListPlants` ([02](02-account-login.md)).
`Functions.SyncInpianti` (`Utils/Functions.java:190`) merges into prefs `DevsTS`: for a Polaris device (`LVDV_Type == PROAIR`, `:222`) whose local `ControlUnit` is **offline**, the server entry replaces the cached one only if the server `LastAddTimezone` is newer; online/unknown ones are replaced unconditionally (`:223-240`).

## Add an existing CU (already on the cloud)
`SetNameAndPinActivity` with `mode == 2` (`Activity/Config/SetNameAndPinActivity.java:136-145`): `POST /api/v1/AddUserToDevice` (type 8, handler `connUsrUC :874`):
```json
{"PIN":"1234","Serial":"<serial>","isPico":false,"PlantId":<id>,
 "token":"<FCM>","platform":"fcm2","type_dev":0}
```
(`Model/Device_OP.java:5-12`; Gson field names, `type_dev` never set for CU so default 0 - inferred.) `ResCode 0` -> `savsercerUc()`; non-zero or HTTP 400 -> toast `au_errorAddUser`. PIN verified server side (inferred). Compare PICO: same endpoint, `isPico:true`.

## Provision a new CU online (cloud part)
Local half (join `POLARIS_<serial>` AP, send Wi-Fi credentials over TCP 1235, `Constants.ip="10.0.0.1"`, `port=1235`: `Utils/Constants.java:315,319`) is in [../local-flows/README.md](../local-flows/README.md). `ConfigActivity.sendconfig_` (`Activity/Config/ConfigActivity.java:105-162`), setup mode 1 (online):
1. TCP `configCu(pin, ...)` returns `{res:1, ser:"<serial>"}`.
2. App builds `Device_OP` (above) as `payload` and an `AddNewCU` body `cmd` (`:121-144`):
```json
{"Pin":"<PIN>","Name":"<name>","Icon":<n>,"Serial":"<serial>","PhoneDate":"yyyy-MM-dd'T'HH:mm:ss.SSS'Z'","cmd":""}
```
3. `unbidNetwork()` then `tryNewCU()` (`:242-260`): after 5 s delay `POST /api/v1/AddNewCU` (type 17, `ThreadWebService.addNewCu :1485`). `ResCode 0` -> `times = CONFIG_TIMES (40)`, go to step 4. Null/other -> `times--`, retry; 401 -> "session expired" + login screen.
4. `checkCentralina()` (`:219-240`): after 5 s `POST /api/v1/CheckConfigCU` (type 18, `checkConfigCU :1546`) with the `Device_OP` payload. `ResCode 0` -> `addCentralinaOnline()` (`:262-280`): cache the CU as online, add device to plant (`LVDV_Type 0`, `LastAddTimezone` = now, `addDevToPlant :287`). Otherwise repeat until `times == 0` -> `error()`. Worst case about 40 x (5 s + RTT) per phase.
Offline-mode config (`mode != 1`) never touches the cloud (`ConfigActivity.java:164-196`).

## Delete a CU
`ControlUnitActivity.cancellacentralina()` (`:944`): offline CU -> local prefs only. Online CU -> `DELETE /api/v1/DeleteDevice` (type 10) body `{"deviceID": <LVDV_Id>, "token":"<FCM>", "platform":"fcm2"}` (`Device_OP.DeviceOp :78-82`, call `:983-988`). `ResCode 0` -> `ControlUnit.deleteCufromPref` + finish (`ThreadWebService.deleteUsrfromUC :942-1040`). Local device record is removed first (`Device.deleteDevFromPref`, `:959`), same optimistic-delete quirk as PICO.
Plant delete/insert/update: same as PICO (`DeletePlant`, `InsertPlant`, `UpdatePlant`).

## Legacy `GetHome` / `DeleteUserFromCU` path
`HomeActivity` (pre-plant UI) still exists: `GET /api/v1/GetHome` (type 9, `HomeActivity.java:202`) returns a raw JSON **array** of CUs (`ControlUnit.setCUServer`, `Model/ControlUnit.java:406-436`): `Name, Serial, FWVer, IsOFF, IsCooling, OperatingModeCooling, LastConfigUpdate, LastSyncUpdate, NumErrors, Icon`. Delete uses `DELETE /api/v2/DeleteUserFromCU` with `CUOperationInfo {usrName, cuSerial, token, platform}` (`HomeActivity.java:223-229`, `Model/CUOperationInfo.java:9-23`). No code starts `HomeActivity` (no `HomeActivity.class` caller found; only the manifest, `AndroidManifest.xml:245`), so this path is dead in the current UI (inferred). `ConnectUserToCU` (`res/values/strings.xml:820`), `AddUserToDeviceV2` (`:815`) have no caller in the Polaris code read.
