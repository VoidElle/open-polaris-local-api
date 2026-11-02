# Provisioning (join CU, scan Wi-Fi, config, PIN)

Paths relative to `.../Export-Pico/sources/it/tecnosystemi/TS`. Cloud registration steps (`AddNewCu`, `CheckConfigCu`, `AddUserToDevice`) are out of scope: `../http-flows/README.md`.

## 1. Access points and passwords

| AP SSID | Password | Purpose | Ref |
|---|---|---|---|
| `POLARIS_CONFIG` | `PWD_CONFIG` | factory/config AP of an unconfigured CU | `Utils/Constants.java:274,283`; used `Activity/Config/EnableWifiVCActivity.java:85-86` |
| `POLARIS_<serial>` | `TS_<serial>` | AP of an already configured CU (offline use / re-pair) | `Constants.java:275,284`; `SetNameAndPinActivity.java:149-150` |
| `POLARIS_UPDATE` | `TS123456` | bootloader AP, see 05 | `Constants.java:273,282` |

CU AP IP is `10.0.0.1:1235` (01 sec. 2). Phone join: `BaseActivity.connectToWifi` (`Activity/BaseActivity.java:1552`+), location permission + GPS required (`:1565-1572,1599-1606`); on API >= 29 uses a scan receiver and `NetworkCallback`/bind (`:1636-1700`, `:1880-1900`).

## 2. Setup modes (`INTENT_SETUPMODE`)

Selected in `ChooseTypeVCActivity.btnProc` (`Activity/Config/ChooseTypeVCActivity.java:72-92`): 2 and 4 -> `SetNameAndPinActivity`; 1 and 3 -> `EnableWifiVCActivity`. Labels are string resources (not read), so the meaning below is deduced from the code paths (inferred):

| Mode | Flow | Result |
|---|---|---|
| 1 | join `POLARIS_CONFIG` -> name+PIN -> `scan_wifi` -> pick SSID -> `config` (offline=0) -> cloud add | CU on home Wi-Fi, cloud-registered (`ConfigActivity.java:104-160`) |
| 2 | serial + PIN typed -> cloud `AddUserToDevice` | add existing cloud CU to this account (no CU traffic) (`SetNameAndPinActivity.java:131-146`) |
| 3 | join `POLARIS_CONFIG` -> name+PIN -> `config` (offline=1) | AP-only CU, stored `offline=true` (`SetNameAndPinActivity.java:109-118`, `ConfigActivity.java:164-185`) |
| 4 | serial+PIN+name -> join `POLARIS_<serial>` / `TS_<serial>` -> `check_pin` | add existing CU as offline device (`SetNameAndPinActivity.java:149-163,213-250`) |

## 3. `scan_wifi`

Request (`Commands/MySocket.java:253-271`, `Cmd.GetWifi`): `{"c":"scan_wifi","pin":"-1"}`, read timeout 15 s (`useLong`).

Reply (`Commands/Cmd.java:66-88`, `Model/WiFi.java:17-33`):

```json
{"c":"scan_wifi","aps":[{"id":"MySSID","sec":1,"rssi":-55,"mac":"AA:BB:.."}]}
```

- `id` = SSID, `sec` int (0 = open; `isCrip()` is later sent as `wifi_sec`), `rssi` and `mac` optional (default 0 / `""`).
- Duplicate SSIDs are dropped, first wins (`ChooseWifiActivity.java:135-148`). App sleeps 2 s before parsing (`:128`). On parse failure retries the whole scan up to 5 times (`:153-160`).
- Password prompt shown for secured networks (`protectedwifi`, `:163-205`); empty password sent as `""` (`MySocket.java:288-290`).

## 4. `config`

Request (`MySocket.java:273-306`, `Cmd.java:23-52`; Gson with `disableHtmlEscaping`):

Online (`offline:0`):

```json
{"c":"config","pin":"1234","offline":0,"wifi_pwd":"secret","wifi_sec":1,"wifi_ssid":"MySSID","wifi_mac":"AA:BB:.."}
```

Offline (`offline:1`): `{"c":"config","pin":"1234","offline":1}` (no Wi-Fi fields).

Reply: `res == 1` and `ser` (serial, `Constants.JSON_SER="ser"`, `Utils/Constants.java:186`); empty serial = failure (`ConfigActivity.java:116-136,166-190`). Read timeout 15 s.

Retry: if the reply is `null`/empty and `tryrecc < maxtryrecc (10)`, the app drops the Wi-Fi (`disconnectFromWIfi`), sleeps 1 s, re-joins `POLARIS_CONFIG` and re-sends (`ConfigActivity.java:56,115-121,200-216`).

After success (mode 1): app unbinds the network, then polls the cloud: `AddNewCu` then `CheckConfigCu`, every 5 s, `times = 40` attempts (`ConfigActivity.java:55,222-260`). Mode 3: serial saved locally (`addcentralina(serial, true)`).

## 5. `check_pin`

Request `{"c":"check_pin","pin":"<pin>"}` (`MySocket.java:308-314`). Reply: `res == 1` = PIN accepted; any other `res` -> error toast; `null` -> generic error (`SetNameAndPinActivity.java:213-250`). Also used with `pin:""` as a connectivity probe (01 sec. 2). PIN input rule: exactly 4 digits (`SetNameAndPinActivity.java:266-289`).

## 6. Persisted result

`ControlUnit.saveCuInPref(name, serial, pin, ip="", icon, activity, offline)` (`Model/ControlUnit.java:735-770`): stores `Pin` and `PinOffline` both = entered PIN, `Ip = ""`, `isOffline` per mode. LAN IP gets filled later from cloud state.

## 7. Gaps vs a headless client

- There is no way to read serial, name or firmware over TCP in the app: serial comes from `config` reply `ser` only (inferred; `stato*` parsers ignore such keys, 02 sec. 2).
- No command to change PIN, name or Wi-Fi after setup in the local protocol (name is changed app-side; `upd_zona` carries zone name).

## 8. Open questions

- Wire semantics of `wifi_sec` (only the scan's `sec` int is echoed back).
- Whether `config` with `offline:1` leaves the CU Wi-Fi client off or keeps previous credentials.
- Labels of modes 1..4 (string resources not in the decompiled sources read).
