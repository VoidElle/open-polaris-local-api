# Firmware update (bootloader over TCP)

Paths relative to `.../Export-Pico/sources/it/tecnosystemi/TS`. The firmware catalog and file download are cloud HTTP (`../http-flows/README.md`); only the local binary protocol is described here. PICO OTA (`ota_start`, TCP 40060) is a different mechanism and out of scope.

## 1. Entry points

- Standalone: CU menu -> `IstrBootloaderActivity` (instructions) -> `BootloaderActivity`.
- During setup: `VerFWActivity.btnVerFw` downloads the catalog then opens `IstrBootloaderActivity` (`Activity/Config/VerFWActivity.java:38-62`).
- Instruction screen joins `POLARIS_UPDATE` / `TS123456` (`Activity/IstrBootloaderActivity.java:63-80`, `Utils/Constants.java:273,282`) then starts `BootloaderActivity`. User must have put the CU in update mode (physical step, text in resources; inferred).

## 2. Cloud side (summary)

`ThreadDowloadFirmWare` GETs the catalog (`R.string.uri_infoFrameWork`), a JSON array of objects with `Path`, `NumByte`, `Version`, `ChangeLogIt`, `ChangeLogEn`, `MicroType`, `PolarisType`, `LVDV_Type`, `MinCleanFlashVr`, `MaxCleanFlashVr` (`Threads/ThreadDowloadFirmWare.java:89-170`; keys `Utils/Constants.java:127-131,187`), stores it in prefs `infofw` and downloads missing `.s19` files into the app dir `FWDir` (`Constants.java:60,214`; `ThreadDowloadFirmWare.java:~385` `uri_FrameWork?filename=<Path>`). Developer mode (`modesviluppatoreBootloader`) instead reads `Download/polaris.s19` or a picked file (`BootloaderActivity.java:~690,806-830`).

## 3. Binary framing (`Commands/MySocketBootLoader.java`)

Same host/port as runtime (`Constants.ip:port`, `MySocketBootLoader.java:159`). Not JSON. One persistent socket reused across commands (`socket` static, `:111-112`), connect timeout 10 s (1 s when `lesstimeout`), read timeout 10 s (`:57-75`). Per command: up to 5 attempts (`:159`), sleep 1 s after an exception unless the command is `writeID` (`:128-133`); exception drops the socket.

Frame request (`prepareDatagram`, `:233-239`): `0x2A ('*')`, `len`, `cmd`, payload..., `0x0D`; `len` counts the whole frame.

| Cmd char | Hex | Name | Payload | Notes |
|---|---|---|---|---|
| `:` | 3A | `hwVer` | none | reply bytes: `[3..4]` polarisType LE, `[5..6]` microType LE (`BootloaderActivity.java:171-199`) |
| 0x0F | 0F | `fwVer` | none | `[3],[4],[5]` -> `"%02d.%02d.%02d"` (`:496-508`) |
| `5` | 35 | `bootver` | none | `[3..5]` kept for 3.x/4.x compatibility check |
| `0` | 30 | `cleanFlash` | none | ack = `reply[3] == 9` (`:204-211`) |
| `1` | 31 | `writeID` (chunk) | S3 record bytes | one frame per record, ack `reply[3] == 9` |
| `2` | 32 | `readCRC` | none | CRC16 = `reply[3] | reply[4]<<8` |
| `6` | 36 | `eraseFlash` | none | optional, ack `[3]==9` |
| `4` | 34 | `reboot` | none | socket closed after |

- Ack byte `9` (`ok`), `8` (`error`) constants at `:30-34`. A reply whose first byte is `'A'` (0x41) is treated as "not ready" and retried (`:119`; also `getHW` waits 5 s and asks again if `hwVer[0]==0x41`, `BootloaderActivity.java:165-170`).
- Hex-encoded transport inside the app only (`printByteArray`/`hexStringToByteArray`); raw bytes on the wire.

## 4. Update sequence

1. Join `POLARIS_UPDATE`; sleep 5 s; `hwVer`; filter catalog by `MicroType` (and `PolarisType` if known) and `LVDV_Type` absent or 0 (`BootloaderActivity.java:153-250`). Old bootloader replies with fewer than 6 bytes (`[0]==0x2A, [1]==5`): `polaristype=-1`, accepts microType 0 or 1090 entries.
2. `fwVer` + `bootver`; compare with `MinCleanFlashVr`/`MaxCleanFlashVr`: version outside range, or `255.255.255` / `00.00.00`, triggers a warning dialog offering a flash-erase update (`controlloVersione`, `:529-620`). For 4.x firmware the bootloader version must be >= `major4x.minor4x.release4x` (`checkVr3x4x`, `:625-650`).
3. Parse `.s19`: keep only lines starting `S3`; payload = `line[4 : len-2]` hex (drops `S3`, count, checksum; keeps 4-byte address + data) (`:697-705`).
4. `cleanFlash` (cmd `0`); on ack send every record with `writeID`, progress every `size/100` records; per record 5 retries then abort (`writeFW`, `:240-285`).
5. `readCRC`; compare with locally computed CRC16 (poly 0x1021, init 0xFFFF, MSB first) over all sent record bytes from index 4 on (data only, address skipped) (`computeCRCFirmware`/`computeCRCFirmwareSent`, `:~340-420`). Mismatch -> failure.
6. If "erase flash" chosen: `eraseFlash` (cmd `6`) then `reboot`; else `reboot` (cmd `4`).
7. Success UI; set result OK, return.

## 5. Resume

`lastFWPK` = index of last acked record. On connection loss the UI offers "retry": reconnect to `POLARIS_UPDATE`, `readCRC`, compare with local CRC of `sentmsg`; if device is one record ahead (CRC matches after adding record `lastFWPK+1`) advance, else restart from 0 (`readCRCForRetry`, `:318-345`). Max `tries` managed in `BootloaderActivity` (`:370-440`). Android 14 (SDK 34) skips `bindProcessToNetwork` in this activity (`BaseActivity.java:1611-1612`).

## 6. Open questions

- Reply layout for `hwVer` of newest bootloaders beyond bytes 3..6.
- Meaning of bytes after `[5]` in `fwVer`.
- Physical procedure to enter update mode (user instructions are resources).
- Hash/signature of `.s19`: none observed on the app side; integrity is only the CRC16.
