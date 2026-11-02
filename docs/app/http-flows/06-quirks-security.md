# 06 - Quirks and security notes (Polaris)

Observed in the app. Relevant if a client reimplements this API. PICO-shared auth/crypto items are condensed; see `open-pico-local-api/docs/app/http-flows/06-quirks-security.md` for the full list.

## Auth and crypto (shared)
- Basic password hard-coded `PwdProAir`; user = email after login, `UsrProAir` before (`Threads/WebClientDevWrapper.java:103-107`). Real auth is the `Token` header.
- `FIX_TOKEN` hard-coded for unauthenticated calls (`Utils/Constants.java:57`, redacted).
- Password and rolling token use AES-CBC with a key from the public `android_id[0:8]` + fixed salt, zero IV. Encryption, not hashing; `DeviceId` is sent in the login body (`LoginActivity.java:298-306`).
- **Polaris PIN** (4 digits typed by the user, `checkPin :130`) travels in clear in the URL query (`GetCUState`, `GetTW`, `SendRestoreCmd`) and in JSON bodies (`Pin` and inner `pin`), and is stored in prefs. TLS is the only protection.

## Token / session bugs (shared)
- `savepref` stores `this.token` (= `FIX_TOKEN`) under `PREF_TOKEN`, not the server token (`ThreadWebService.java:817-822`).
- `Constants.token != ""` compares references (`ThreadWebService.java:1079`, repeated in every handler).
- `calcNewToken` can return `null` and the call still goes out (`Utils/Functions.java:544-575`).
- Counter increments per call incl. the 5 s poll; two clients on one account may collide (inferred).
- Session 1 h hard, no refresh (`BaseActivity.java:2066-2081`).

## Polaris-specific
- **Silent PIN failure in the poll**: only the first `GetCUState` call (type 12) surfaces `ResCode 2`; later polls (type 11) swallow it and the UI shows "status not synchronized" (error bit 5) instead of a PIN error (`ThreadWebService.java:1097-1115`).
- `BaseActivity.pinerror()` needs two consecutive PIN errors to clear the stored PIN (`BaseActivity.java:1482-1493`).
- **LAN-first writes with cloud fallback**: a command already delivered over TCP is also POSTed (with `?create_command=false`) (`ControlUnitActivity.java:743-782`); if the CU answers over TCP with a `res` other than 1 the app toasts failure and aborts without trying the cloud (`:748-763`); a missing or empty reply falls through to the cloud.
- Commands are queued server-side with no ack; UI says "applied within 10 minutes" for FW < 4 (`ThreadWebService.java:1175-1181`). Optimistic UI is reverted for zones only on a failed POST (`resetTemp`).
- Double-encoded payloads: `Cmd`/`cmd` is JSON in a JSON string; `GetPlants` `ResDescr` and login `ListPlants` likewise.
- Inconsistent key casing across endpoints (`Cmd` vs `cmd`, `Pin` vs `pin`, `PIN` in query vs `Pin` in body vs `PIN` in `Device_OP`) - match exactly.
- `GetCUState`/`GetTW` replies have no `ResCode` on success but an error body (`ResCode != 0`) is treated as "no data".
- `CheckConfigCU`/`AddNewCU` polling: up to 40 attempts x 5 s per phase; 401 sends the user to login (`ConfigActivity.java:219-260`).
- `SendRestoreCmd` is a **GET** with side effects (resets CU configuration), authorised only by serial+PIN in the query (`ControlUnitActivity.java:1195`).
- Temperatures are tenths of a degree in strings (`"215"`); crono times are 15-minute indexes; empty crono slot is `{i:0,f:0,t:240}` (`Crono.java:89-96`).

## Dead / unreachable code
- `resetConn` / `GET /api/v1/ResetConnection`: handler and activity method exist, menu entry is built then discarded (`ControlUnitActivity.java:1007`, `:1171-1177`).
- `HomeActivity` + `GetHome` + `DeleteUserFromCU`: no caller starts `HomeActivity` (inferred, see [03](03-plants-devices.md)).
- `ThreadWebService.run` switch: cases 32 and 33 have no `break` (`:177-182`), shared with PICO; not Polaris-relevant (class casts fail silently).
- Success toast "applied within 10 minutes" survives in the strings although FW >= 4 shows plain OK.
- `Constants.modesviluppatore` (developer toasts, last-sync label) and `modesviluppatoreBootloader` (local `polaris.s19`) are compile-time `false` (`Utils/Constants.java:317-318`).

## Library gaps vs cloud (open_polaris_local_api)
1. No cloud client exists (verified: no HTTP imports in `client.py`/`models.py`/`polaris_auto_discovery.py`).
2. CU error bitmask: cloud `GetCUState.Errors`, library reads `NumErrors`/`err_cu` (`models.py:258-259`); `Errors` would be dropped. Fix before feeding cloud JSON.
3. Zone `IsMaster` read as `isMaster` (`models.py:154-156`); `IsCooling` read as `isCooling` on zones (`:142`).
4. `_parse_temp` heuristic (`>= 100` -> /10) breaks cloud tenths below 10.0 C (`models.py:40-52`); cloud always sends tenths.
5. Error text tables differ from the app resources: bits 5-7 are all "System status not synchronized" in the app (`res/values/arrays.xml:33-35`, `:43-45`); library has "E6/E7 - Server Error" and "Network error" (`models.py:11-35`).
6. `IsCronoActive`, `COff`, `LastSyncUpdate`, `LastConfigUpdate`, `Icon` are not modelled.

## Reimplementation hints
1. Login ([02](02-account-login.md)); keep `Token`; re-login before 1 h.
2. Before each later call advance the token counter; Basic user = email.
3. Poll `GET /api/v1/GetCUState?cuSerial=&PIN=` every 5 s; handle the first call separately for PIN errors.
4. Parse with the existing PascalCase fallbacks after fixing items 2-4 above.
5. Write with `UpdateCUData` / `UpdateZonaData` using the same inner JSON as the local `upd_cu` / `upd_zona`, double-encoded; expect delivery latency, confirm via the next poll.
6. Use `?create_command=false` only if you delivered the same command over TCP yourself.
