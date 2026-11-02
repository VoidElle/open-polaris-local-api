# Crono programs (`get_fasce` / `upd_fasce`)

Paths relative to `.../TS`. Transport: `01-transport.md`.

## 1. Model

- Per zone: 7 days x 4 slots (`Zona.azzeracrono`, `Model/Zona.java:342-351`). Day index 0..6 = Lun..Dom (`Constants.JSON_GIORNI`, `Utils/Constants.java:329`; the local protocol uses the numeric index as JSON key).
- Slot = `Crono{Start, End, Temp}` (`Model/Crono.java:11-20`). Wire time unit = 15 minutes (`value = minutes/15`, `Crono.java:47-71`; back: `convertTimeToNormal`, `:190-197`, `24:00` shown as `00:00`). Wire temp = deg C x 10 integer (`commandUpd`, `:73-87`).

## 2. Read: `get_fasce` (offline only)

Request (`Activity/CronoSummaryActivity.java:96-102`):

```json
{"c":"get_fasce","pin":"<PinOffline>","id_zona":1}
```

Reply parsed in `getTWOffline` (`:127-150`): keys `"0".."6"`, each an array of slot objects `{"i":start,"f":end,"t":temp}` (`Constants.JSON_COMMAND_START="i"`, `_END="f"`, `_TEMP="t"`, `Utils/Constants.java:101-103`; `Crono.JsonOffline`, `Crono.java:173-188`). Array index = slot index. Then `normalizzaOrario`: values `"0"`/`"0"` (`COMMANDSENT="0"`) -> empty slot; otherwise `n*15` min -> `HH:mm`; temp `/10`.

Online CU: read via cloud (`GetTW`, out of scope); `get_fasce` over LAN is NOT used by the app (`CronoSummaryActivity.java:~118-124`).

## 3. Write: `upd_fasce`

Built by `Zona.updCronoCommand(pin)` (`Model/Zona.java:413-433`):

```json
{"c":"upd_fasce","id_zona":1,"pin":"1234",
 "0":[{"i":28,"f":36,"t":210},{"i":0,"f":0,"t":240},{"i":0,"f":0,"t":240},{"i":0,"f":0,"t":240}],
 "1":[...], ... "6":[...]}
```

- Always full replace: 7 keys, 4 objects each. Empty/null slot -> `{"i":0,"f":0,"t":240}` (`Crono.commandUpdVoid`, `Crono.java:89-100`).
- Validation before send (`CronoSetActivity.controllofasce`, `:488-...`): each slot `isok()` (start/end/temp all set or all empty, `end > start` via `Functions.differencetime`, temp numeric; `Crono.java:102-117`) and each slot starts at or after the previous slot's end (`CronoSetActivity.java:501-510`).
- Transport: offline -> TCP `10.0.0.1` (`CronoSetActivity.java:413`); online -> LAN TCP `cu.getIp()` with `pin` = `getPin()` (`:436-437`), `res != 1` -> toast and stop; else cloud `UpdTW` with `create_command=false` if LAN `res==1` (`:465`).
- Success = `res == 1`.

## 4. Zone mode flag

Switching a zone between manual and crono is done through `upd_zona.is_crono` (see 02 sec. 4.2), not via `upd_fasce`. `crono_on` in state = "current slot active" (`Zona.setFasciaAttiva`).

## 5. Open questions

- Day-of-week mapping 0 = Monday is inferred from `JSON_GIORNI` order; the CU firmware side is not visible.
- Reply body of `upd_fasce` (only `res` read).
