# 02 - Account and login (Polaris view)

Identical to PICO; condensed and re-verified against source. Full write-up: `open-pico-local-api/docs/app/http-flows/02-account-login.md`. Only Polaris-relevant points are repeated.

## Login
`LoginActivity.login()` (`Activity/LoginActivity.java:285-311`): validate email + non-empty password, then
```json
{"Username":"<email>","Password":"<AES(pwd)>","DeviceId":"<android_id>",
 "Timezone":"Europe@Rome","TokenPush":"<FCM token>","Platform":"fcm2"}
```
(`Model/LoginModel.java:9-21`; `Platform` = `Constants.NOTIFIC_PLAT`, `Utils/Constants.java:197`).
- `Password` = AES-CBC (zero IV) base64, key from `android_id[0:8] + "ns91wr48"` -> reversible, not a hash (`LoginActivity.java:298`).
- `POST /apiTS/v2/Login`, Basic `UsrProAir:PwdProAir`, `Token: FIX_TOKEN` (`ThreadWebService.logIn`, `:684-690`).
- No auto-login; remember-me only prefills the form.

### `ResCode` (HTTP 200 body, `ThreadWebService.java:735-805`)
| ResCode | Action |
|---------|--------|
| 0 | success |
| 1 / 2 / 3 / 4 | toast: wrong user-or-pwd / user must confirm email / blocked / not found |
| 5 | nothing |
| 6 | `ChangePwdActivity` (temporary password) |
| 7 | toast: request new temporary password |
| 10 | privacy/ToS not accepted -> `GDPRActivity`, then `POST /apiTS/v2/AcceptTermsOfUse` (type 32) |

### On success (`ResCode 0`, `:700-735`, `savepref :817`)
- `Constants.token = Token` (memory only), `PREF_TOKEN_DATE = now`, `PREF_USER_ID = ID`; `Constants.user = email` (Basic user from now on).
- Optional: `ResetPin`, `LastFWVr`, `LastVrAndroid`, `LastVrAndroidText`, `MarketingAccepted`, `ListTimezone` (PICO only), `ListRecipe` (Modbus, out of scope).
- **`ListPlants`** (JSON string -> `ArrayList<Plant>`) -> `Functions.SyncInpianti` (`Utils/Functions.java:190`). This is where Polaris devices (`LVDV_Type 0`) first arrive; see [03](03-plants-devices.md).
- Navigation: exactly one plant -> `TSDeviceListActivity`, else `TSHomeActivity`. Tapping a `LVDV_Type == 0` device opens `ControlUnitActivity` (`TSDeviceListActivity.java:256-258`, `startCUActivity :269-279`).

## Session
`BaseActivity.onResume` (`Activity/BaseActivity.java:2066-2081`): if `PREF_TOKEN_DATE` older than 1 h or `Constants.token` empty -> toast `sessioneScaduta`, restart `LoginActivity`. Not sliding; API calls do not refresh it. The Polaris 5 s poll only runs while a CU/zone screen is resumed, so it neither keeps the session alive nor survives expiry.

## Other account calls (unchanged vs PICO)
| Action | Call |
|--------|------|
| Check email | `GET /apiTS/v1/CheckEmail?email=` (type 1; `ResCode 9` = exists) |
| Sign-up | `POST /apiTS/v2/RegisterUser` (type 0) |
| Forgot password | `POST /apiTS/v1/ForgotPwd` (type 3) |
| Change password | `POST /apiTS/v2/ChangePwd` (type 2, handler `logIn`) |
| GDPR | `POST /apiTS/v2/AcceptTermsOfUse` (type 32) |
| Delete account | `DELETE /api/v1/DeleteUser` (type 20; `ThreadWebService.delUser :579`) |
Demo mode (`Constants.ISDEMO`): no network; `ControlUnitActivity` loads `DataClass.controlunit_list` instead (`ControlUnitActivity.java:68-77`), poll not started (`:1022-1026`).
No logout call found (inferred from absence).
