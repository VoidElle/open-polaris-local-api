# 01 - HTTP transport and auth (Polaris view)

Shared with PICO; condensed and re-verified. Full PICO write-up: `open-pico-local-api/docs/app/http-flows/01-http-transport-auth.md`.

## Layers
`Activity` -> `new ThreadWebService(activity, method, type, url, jsonBody, params[, showProgress]).start()` (`Threads/ThreadWebService.java:65`) -> `WebClientDevWrapper.getNewHttpClient(url, body, token, user, method, type)` (`Threads/WebClientDevWrapper.java:21`) -> `HttpURLConnection`.
`run()` (`:92`) switches on `type` and calls one handler that parses the reply and calls back into the activity. No retry layer, no OkHttp/Retrofit. Any exception in the wrapper returns `null` -> toast `resCodeError` (`:35-39`).

## Wire format
| Item | Value |
|------|-------|
| Base URL (Polaris) | `uriWebService_POLARIS` = `https://proair.azurewebsites.net` (`res/values/strings.xml:812`). Identical to `uriWebService` (`:810`) and `_PICO` (`:811`) |
| Which constant | `_POLARIS`: `GetCUState`, `UpdateCUData`, `UpdateZonaData`, `UpdateCUDatetime`, `GetTW`, `UpdateTW`, `SendRestoreCmd`, `ResetConnection`, `DeleteDevice` (CU screen), `FWs` (CU screen). Plain `uriWebService`: login, plants, `AddUserToDevice`, `AddNewCU`, `CheckConfigCU`, `GetHome`, `DeleteUserFromCU`, firmware download |
| `method` arg | 0 GET, 1 POST, 2 DELETE (with body), 3 PUT (`WebClientDevWrapper.java:23-37`) |
| Timeouts | connect 15 s, read 15 s (`:49-50`, `:99-100`) |
| `Authorization` | `Basic base64("<Constants.user>:PwdProAir")`; before login user is `UsrProAir` (`:52`, `:103-107`) |
| `Token` | login/sign-up/forgot/GDPR: fixed `Constants.FIX_TOKEN` (`Utils/Constants.java:57`, redacted here); afterwards rolling token (below). Every handler falls back to `FIX_TOKEN` while `Constants.token` is empty (identical block at the top of each handler, e.g. `ThreadWebService.java:1079-1084`) |
| `UserObj-Agent` | `benincapp`, GET only (`:56`) |
| Body | `application/json`, UTF-8 |
| Query string | CU endpoints put serial + PIN in the query: `?cuSerial=<SER>&PIN=<PIN>` (`ControlUnitActivity.java:66`, `CronoSummaryActivity.java:118` adds `&zoneID=`) or in the body |

## Rolling token (`Functions.calcNewToken`, `Utils/Functions.java:544-575`)
Same scheme as PICO: key = SHA-256-derived from `android_id[0:8] + "ns91wr48"` (`Constants.SALT`, `Utils/Constants.java:252`), `AES/CBC/PKCS7`, zero IV (`Utils/AESCrypt.java:16-22`). Server token decrypts to `"<text>_<counter>"`; each call decrypts, counter+1, re-encrypts, strips CR/LF, stores in prefs `cont_token` / `TOKENVALUE`. Decrypt failure returns `null` -> request goes out with `Token: null` (inferred: 401).
Retry on 401 exists only for firmware calls (5 attempts, `Threads/ThreadDowloadFirmWare.java:75-84`, `:394-401`) and `BaseActivity.makeApiCall` (5 attempts, then `unauth()`; `Activity/BaseActivity.java:2186-2204`). The Polaris state/command handlers do not retry. `AddNewCU`/`CheckConfigCU` on 401 toast "session expired" and open `LoginActivity` (`ThreadWebService.java:1531-1541`, `:1597-1607`).

## Dispatch table: types used by Polaris (`ThreadWebService.run`, `:92-195`)
| type | Handler | Endpoint (method) | Used by |
|------|---------|-------------------|---------|
| 2 | `logIn` | `/apiTS/v2/Login`, `/apiTS/v2/ChangePwd` (POST) | Login, ChangePwd |
| 3, 0, 1, 32 | account | `ForgotPwd`, `RegisterUser`, `CheckEmail`, `AcceptTermsOfUse` | see [02](02-account-login.md) |
| 8 | `connUsrUC` | `/api/v1/AddUserToDevice` (POST) | `SetNameAndPinActivity.java:145` (add existing CU) |
| 9 | `getHome` | `/api/v1/GetHome` (GET) | legacy `HomeActivity.java:202` |
| 10 | `deleteUsrfromUC` | `/api/v1/DeleteDevice` (DELETE); legacy `/api/v2/DeleteUserFromCU` | `ControlUnitActivity.java:988`, `HomeActivity.java:229` |
| 11 / 12 | `getCuState` | `/api/v1/GetCUState?cuSerial=&PIN=` (GET) | poll; 12 = first call (PIN errors surfaced), 11 = later polls |
| 13 | `updState` | `/api/v1/UpdateCUData`, `/api/v1/UpdateZonaData` (POST) | `ControlUnitActivity.java:791,930`, `ZoneActivity.java:537` |
| 14 | `getTW` | `/api/v1/GetTW?cuSerial=&zoneID=&PIN=` (GET) | `CronoSummaryActivity.java:118` |
| 15 | `updTW` | `/api/v1/UpdateTW` (POST) | `CronoSetActivity.java:470` |
| 16 | `updCUDatetime` | `/api/v1/UpdateCUDatetime` (POST) | `ControlUnitActivity.java:354` |
| 17 | `addNewCu` | `/api/v1/AddNewCU` (POST) | `ConfigActivity.java:253` |
| 18 | `checkConfigCU` | `/api/v4/CheckConfigCU` (POST) | `ConfigActivity.java:232` |
| 19 | `resetConn` | `/api/v1/ResetConnection?cuSerial=&PIN=` (GET) | `ControlUnitActivity.java:1008` (unreachable, see [06](06-quirks-security.md)) |
| 20 | `delUser` | `/api/v1/DeleteUser` (DELETE) | delete account |
| 21 | `restConfig` | `/api/v1/SendRestoreCmd?cuSerial=&PIN=` (GET) | `ControlUnitActivity.java:1195` |
| 22, 23 | plants | `InsertPlant`/`UpdatePlant` (POST), `GetPlants` (GET) | see [03](03-plants-devices.md) |
| 4, 5 | firmware | `/api/v4/FWs`, `/api/v1/FW?filename=` (GET) | `ThreadDowloadFirmWare`, see [05](05-firmware-push.md) |
| 24-31, 33, 34 | PICO/VMC/6X | out of scope | |
Paths: `res/values/strings.xml:813-848`. Types 11 and 12 share a handler (`ThreadWebService.java:119-124`); 13/15/16 are the write paths.

## Response convention
Two shapes:
- **Writes and account**: `{"ResCode": n, "ResDescr": "..."}`; HTTP 200 for OK, 400 for logical errors with same body.
- **`GetCUState` / `GetTW` / `GetHome`**: the data object (or array) itself, no wrapper. The handler tests `has("ResCode")` and, if present and non-zero, treats the reply as an error (`ThreadWebService.java:1097-1100`, `:1281-1290`).

| ResCode | Meaning (Polaris) |
|---------|-------------------|
| 0 | OK |
| 2 | wrong PIN -> `pinerror()` toast `pin_error` (`ThreadWebService.java:1701-1709`, `res/values/strings.xml:725`) |
| 9 | `SendRestoreCmd` failed (`:526-576`) |
Login values: [02-account-login.md](02-account-login.md). Handlers check `ResCode` only when present; missing -> generic `msg_commandKo` toast. A 400 from `AddUserToDevice` shows `au_errorAddUser` regardless of `ResCode` (`:874-940`).
