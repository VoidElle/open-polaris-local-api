# 05 - Firmware catalog and push (Polaris)

## Firmware catalog
Trigger: CU screen menu "Update firmware" (`ha_menuUpdateFW`), shown only when the cached catalog `PREF_INFOFWS` (`"infofw"`) is a non-empty array (`Activity/ControlUnitActivity.java:1099-1115`). Tap sets `gotobooloader = true` and starts `ThreadDowloadFirmWare` with `uriWebService_POLARIS + /api/v4/FWs` (`:1099`). Also started from the home screens and `VerFWActivity` (same code, other base URL constants, all the same host).
1. `GET /api/v4/FWs` (type 4, `Threads/ThreadDowloadFirmWare.java:75-84`), Basic + rolling `Token`, up to 5 attempts while HTTP 401.
2. Reply = JSON array of firmware entries, written verbatim to `PREF_INFOFWS` (`:214`, `:313`). Fields read by the app:

| Field | Use |
|-------|-----|
| `Path` | file name (`:129`, `:159`); download key |
| `NumByte` | expected byte length (`:142`, `:148`) - PICO doc calls this "size" |
| `Version` | shown in the picker, sort key (`Activity/BootloaderActivity.java:263`, `ThreadDowloadFirmWare.java:175`) |
| `LVDV_Type` | Polaris entries have it absent or `0` (`BootloaderActivity.java:261`); other values belong to PICO/VMC/6X |
| `MicroType` | must equal the CU micro id read from the bootloader, or `0`/`1090` when the HW reply is short (`:261`) |
| `PolarisType` | must equal the board type read from the bootloader when known (`:261`; `Constants.JSON_POLARISTYPE`, `Utils/Constants.java:184`) |
| `MinCleanFlashVr`, `MaxCleanFlashVr` | installed-FW range that allows a flash without full erase; `MaxCleanFlashVr == "NULL"` = no upper bound (`BootloaderActivity.java:534-545`) |
| `ChangeLogIt`, `ChangeLogEn` | changelog text, `"NULL"` string = absent (`:276-296`) |
Constants `MemorySize`, `WiFiVersion` exist (`Constants.java:129,189`) but no reader found in the code read.
3. Local folder `FWDir` is synced: files not in the catalog deleted, missing ones downloaded (`:115-150`, `deleteFw :374`).
4. Download: `GET /api/v1/FW?filename=<Path>` (type 5, binary, up to 5 attempts on 401; `downloadFw :382-426`). Saved only if byte length equals `NumByte`; else `ok=false`, toast `ha_syncFWError`.
5. When `gotobooloader` is set, `gotobootloader()` opens `SelectTypeDevActivity` (`TS_TIPO_OP=1`, `ThreadDowloadFirmWare.java:357-371`) which routes to the Polaris instructions screen `IstrBootloaderActivity` (`Activity/TS/SelectTypeDevActivity.java:52`; the device-type branch for CU is inferred from the unsuffixed class name).

## Flashing
Not online. `BootloaderActivity` joins the CU update AP (`POLARIS_UPDATE`, fixed password literal in `BootloaderActivity.java:226`) and pushes the downloaded `.s19` to the board through `MySocketBootLoader` over the local network (details: [../local-flows/README.md](../local-flows/README.md)). Developer mode flashes a local `Download/polaris.s19` instead (`:257`, `:683`). The cloud is only the file source and version catalog; the picker is filtered by the HW ids read over the AP (`:160-200`, `:256-266`).
Login hints: `LastFWVr` (Constants.LastFWVr), `LastVrAndroid`, `LastVrAndroidText` ([02](02-account-login.md)). No forced update found.

## Push notifications (FCM)
- Token: `BaseActivity.FirebaseToken` (`:121`, `:219`), sent as `TokenPush`+`Platform:"fcm2"` at login and as `token`/`platform` in `AddUserToDevice`, `AddNewCU`/`CheckConfigCU` (`Device_OP`), `DeleteDevice`, `DeleteUserFromCU`. Backend uses it to deliver alerts (inferred).
- Receiver: `Utils/MyFirebaseService.onMessageReceived :24` reads `data.message`; the first 6 chars parse as a numeric code (`sendNotification :28-39`): `1` -> "Communication error with the control unit: <rest>" (`res/values/strings.xml:564`), `2` -> PICO communication error. Anything else is shown as-is. Channel `tecnosystemi_channel_ID`.
- Opt-in dialog in `LoginActivity.checkRegNotification :145`, prefs `PREF_REGID_NAME`/`PREF_REGID_SETTING_NAME`.
- Pushes do not update screen state; the 5 s `GetCUState` poll does.
