# Local transport and protocol (POLARIS CU)

Source: JADX export of the Tecnosystemi app. Paths relative to `.../Export-Pico/sources/it/tecnosystemi/TS`. No tag = read in code; "(inferred)" = deduced. Some JADX output is degraded (e.g. `MySocket.MySocketReadAndWrite.doInBackground`, `Commands/MySocket.java:69-128`, control flow is scrambled; behavior below is the reconstructed intent).

Scope: ControlUnit only. Cloud: `../http-flows/README.md`. Firmware transport: `05-firmware-ota.md`.

## 1. Transport map

| Transport | Class | Dest | Port | Use |
|---|---|---|---|---|
| TCP JSON (text) | `Commands/MySocket.java` | AP `10.0.0.1` or CU LAN IP | 1235 | all runtime/provisioning |
| TCP binary | `Commands/MySocketBootLoader.java` | `10.0.0.1` | 1235 (same constants) | firmware upload, see 05 |

`Constants.ip = "10.0.0.1"` (`Utils/Constants.java:315`), `Constants.port = 1235` (`:319`). Port is never read from anywhere else; the LAN path also uses `Constants.port` (`Activity/ControlUnitActivity.java:329`).

## 2. Device IP resolution

| Mode | Condition | Host | Where |
|---|---|---|---|
| Offline (AP) | `cu.isOffline()` | `Constants.ip` = `10.0.0.1` | `Activity/ControlUnitActivity.java:326,718,863`; `Activity/ZoneActivity.java:465`; `Activity/CronoSetActivity.java:413` |
| Online (LAN attempt) | `!isOffline` and `cu.getIp()` non-empty | `cu.getIp()` | `ControlUnitActivity.java:329,747,893`; `ZoneActivity.java:497`; `CronoSetActivity.java:436-437` |

- `cu.getIp()` comes from the cloud state field `IP` (`Utils/Constants.java:110` `JSON_CU_IP="IP"`; parsed `Model/ControlUnit.java:637-638`), kept across state merges (`:707-708`). It is also persisted (`:305`). The CU therefore reports its own LAN IP to the cloud (inferred; the report path is device-side, not in the app).
- If the LAN command fails (empty reply, `res != 1`, exception) the app clears the IP (`ControlUnitActivity.java:344` `cu.setIp("")`, `upd_date` path only) and sends the same command through the cloud (`Threads/ThreadWebService`, out of scope). Cloud call carries `create_command=false` when the LAN call already returned `res==1` (`ControlUnitActivity.java:782, :925; ZoneActivity.java:532; CronoSetActivity.java:465`), else flag `COMMAND10MIN="1"` (`Utils/Constants.java:26`).
- No discovery: no scan, no mDNS, no broadcast. `Threads/ThreadUDPServer.java` (UDP 5678) is never started (see PICO docs).
- Liveness probe in `BaseActivity.connectToWifi`: sends `check_pin` with an empty PIN `""` to `10.0.0.1:1235`; any non-empty reply = "connected" (`Activity/BaseActivity.java:1634-1639`). Used only when already retrying inside the AP flows.

## 3. Wire format

Plain TCP stream, UTF-8 JSON text, no framing/terminator, no length prefix (`PrintWriter.write` + `flush`, `Commands/MySocket.java:206-213`).

Request envelope (Gson, `Commands/Cmd.java:10-21`):

```json
{"c":"stato_r","pin":"1234"}
```

| Field | Meaning | Source |
|---|---|---|
| `c` | command name | `Cmd.java:12` |
| `pin` | device PIN (`Constants.INTENT_PIN="pin"`, `Utils/Constants.java:90`) | `Cmd.java:16` |
| rest | command specific, flat | 02..05 |

Command names (`Commands/Protocols.java:5-17`): `check_pin`, `config`, `get_fasce`, `scan_wifi`, `stato`, `stato_r`, `stato_zona`, `upd_cu`, `upd_date`, `upd_fasce`, `upd_zona` (+ `stato_sync` unused for CU). `Protocols.CMD_NOT_FOUND = 4`, `Protocols.OK = 1` (`:9,18`).

Response: JSON object, `res` int (`Constants.JSON_RES="res"`, `Utils/Constants.java:185`), echoes `c` for `stato_r` (the parser branches on `c == "stato_r"`, `Model/ControlUnit.java:529-534`).

| `res` | Meaning | Evidence |
|---|---|---|
| 1 | OK | `Protocols.java:18`; callers e.g. `ControlUnitActivity.java:720` |
| 4 | command not found (old firmware has no `stato_r`) -> app falls back to `stato` | `Activity/BaseActivity.java:1404-1417` |
| other | error; toast `"Errore Risposta:<n>"` when caller asked for toasts | `Commands/MySocket.java:349-358` |
| no `res` key | treated as failed command (returns `null`) | `MySocket.java:359-372` |

Other codes are not enumerated in the app.

## 4. Connect / send / receive

- One socket per `sendAndReceive` call, closed afterwards (`MySocket.java:121-127`). No keep-alive, no persistent session.
- `connectWithSocket` (`:161-191`): up to 2 tries; each: bind socket to `tobindnet` if set, `setSoTimeout(1000)` (or 15000 if `useLong`), `connect(addr, 1000)`; on failure sleep 800 ms and recreate the socket. After 2 failures it returns the (unconnected) socket (JADX: the caller then skips send).
- `useLong` (15 s read timeout) is set only for `scan_wifi` and `config` (`MySocket.java:262,297`) and consumed (reset) by the next connect.
- Read (`receiveDataFromSocket`, `:215-239`): loop `read(buf[1000])`; append; stop when a read returns `< 1000` bytes; if exactly 1000, sleep 100 ms and read again. So a reply is "complete" at the first short read; no JSON balance check.
- Retry loops (two levels):
  1. Inner (`doInBackground`): `strArr[3]` = `Constants.COMMAND10MIN` = `"1"` attempts (`MySocket.java:243`) -> effectively 1 attempt.
  2. Outer (`commandToCU`, `:316-346`): on `SocketTimeoutException` the inner returns the sentinel `"timeouterr"`; `timeouttimes` (static, init 3, `:45`) is decremented, sleep 500 ms, re-send the same JSON. After 3 timeouts returns `""`. Reset to 3 on any real reply.
  Worst case ~3 x (1 s read + 2 x 1 s connect + 0.8 s) plus 2 x 0.5 s (inferred arithmetic).
- A non-timeout failure (connection refused/reset) yields `""` from the inner loop; `commandToCU` then does `new JSONObject("")` -> exception -> returns `null` (`:347,387-399`).
- `commandToCU(json, ip, port, toastOnError, showProgress, hideProgress)` (`:316`): UI flags only; shows progress dialog on a thread, toasts `msg_commandKo` on empty/invalid replies.
- Idempotency: the same payload is re-sent on timeout with no idp; a command already executed by the CU is executed again (no de-dup in the protocol). Idempotent for `upd_*` setters (absolute values).

## 5. Android network binding

- AP modes need the phone on SSID `POLARIS_CONFIG` / `POLARIS_<serial>` / `POLARIS_UPDATE`. App joins via `BaseActivity.connectToWifi` (`Activity/BaseActivity.java:1552-1900`) and, once on the right SSID, `bindProcessToNetwork(net)` + `MySocket.tobindnet = net` (`:1613-1617`, `:1894-1898`). `Network.bindSocket` is applied to each socket (`MySocket.java:167-170`).
- `Functions.netBinding` (`Utils/Functions.java:701-728`) also binds the process if SSID contains `"POLARIS"`; note it tests `indexOf("POLARIS") > 0`, so an SSID that STARTS with `POLARIS` (index 0) does not match -> falls to `netUnbinding` (quirk; `netBinding` has no caller in the files read, inferred dead code).
- Unbinding: `HomeActivity.java:72`, `TSHomeActivity.java:75`, `BaseActivity.unbidNetwork` (`:1995-2005`).
- None of this applies to the LAN/online path (plain routing on the home Wi-Fi, no bind unless a previous bind is left over).

## 6. Credentials / security

- PIN: 4 digits, validated client-side `length()==4` and numeric (`Activity/Config/SetNameAndPinActivity.java:266-289`). Stored in prefs as `Pin`/`PinOffline` (`Utils/Constants.java:120-121`, `Model/ControlUnit.java:303`).
- Offline CU uses `getPinOffline()`, online uses `getPin()` in `upd_cu` (`Model/ControlUnit.java:320-324`). `saveCuInPref` stores the same PIN in both (`:735-760`).
- `scan_wifi` is sent with `pin:"-1"` (`MySocket.java:260`), `check_pin` can be sent with `""` (see sec. 2).
- No TLS, no HMAC, no nonce. PIN and (during `config`) the Wi-Fi password travel in clear.

## 7. Constants

| Constant | Value | Ref |
|---|---|---|
| AP IP | `10.0.0.1` | `Utils/Constants.java:315` |
| TCP port | 1235 | `:319` |
| Connect timeout | 1000 ms (x2, 800 ms pause) | `MySocket.java:164-185` |
| Read timeout | 1000 ms; 15000 ms for `scan_wifi`/`config` | `:37-38,176-178` |
| Read buffer | 1000 B | `:34,216` |
| Timeout retries | 3 (500 ms apart) | `:45-47,335-343` |
| Poll period | 5000 ms | `Activity/BaseActivity.java:162,1378` |

## 8. Quirks

- Static mutable state (`timeouttimes`, `useLong`, `tobindnet`) shared across threads, no locks.
- `MySocket.IP_actual`/`PORT_actual` declared, never written (`MySocket.java:35-36`).
- Reply parse trusts the first short read; a reply split exactly on a 1000-byte boundary is handled, one split into two short TCP segments is not (inferred).
- `res != 1` replies to polls are discarded (`BaseActivity.offlineResZona`/`offlineResCU`, `:1429-1480`); the UI then shows no data (offline) or an error bit (online, `ControlUnitActivity.java:611-619`).

## 9. Open questions

- Exact meaning of `res` values other than 1 and 4.
- Whether the CU accepts concurrent TCP connections (app never opens two at once from the same activity, but `sendingstate`/`gettingstate` flags only gate its own threads).
- Whether `check_pin` with an empty PIN returns `res=1`, an error code, or just any JSON (the probe only checks "non-empty").
