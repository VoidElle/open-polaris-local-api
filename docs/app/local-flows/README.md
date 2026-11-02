# POLARIS (ControlUnit) local flows (decompiled Tecnosystemi app)

Map of the Polaris 5X "ControlUnit" (CU) local flows derived from `../../../../open-pico-local-api/Export-Pico/sources/it/tecnosystemi/TS` (JADX). `file:line` references are relative to that folder. "(inferred)" = deduced, not read.
Out of scope: PICO, VMC, SeiX, cloud/HTTP (see `../http-flows/README.md`).

| File | Content |
|------|---------|
| [01-transport.md](01-transport.md) | TCP JSON on port 1235, one short socket per command, envelope `{c, pin, ...}`, `res` codes, timeouts/retries, Android network binding, IP resolution (AP `10.0.0.1` vs cloud-provided LAN IP) |
| [02-polaris-runtime.md](02-polaris-runtime.md) | `stato_r` / `stato` / `stato_zona` polling (5 s), parsing (full vs "ridotto"), `upd_cu`, `upd_zona`, `upd_date`, error bitmasks |
| [03-crono.md](03-crono.md) | `get_fasce` / `upd_fasce`: 7 days x 4 slots, 15-minute units |
| [04-provisioning.md](04-provisioning.md) | AP `POLARIS_CONFIG`, `scan_wifi`, `config` (online/offline), `check_pin`, 4 setup modes |
| [05-firmware-ota.md](05-firmware-ota.md) | `POLARIS_UPDATE` AP, binary bootloader protocol (S3 records, CRC-16), resume logic |
| [../diff-app-api.md](../diff-app-api.md) | App vs `open_polaris_local_api` (verified, local + cloud) |

Key points:
- Protocol is NOT the PICO UDP envelope: no `cmd/frm/idp`; command key is `c`, PIN key is `pin`, success is `res == 1` (`Commands/Cmd.java:12-17`, `Commands/Protocols.java:18`).
- Two local modes, chosen by the per-CU `isOffline` flag (`Model/ControlUnit.java:163`): offline = app joined the CU's own AP and talks to fixed `10.0.0.1:1235`; online = commands go first to `cu.getIp():1235` (IP delivered by the cloud state), then fall back to cloud.
- The app NEVER polls state over the home LAN: polling is TCP only in offline/AP mode, otherwise cloud (`Activity/BaseActivity.java:1305-1346`). LAN TCP is used by the app only for write commands (and `upd_date`, `upd_fasce`).
- PIN in clear text on every command; no encryption, no signature.
- `stato_sync` is not a CU command (defined in `Protocols` but used only by VMC/SeiX: `Activity/VMC/VMCActivity.java:161`, `Activity/SEIX/SeiXMainActivity.java:125`).
