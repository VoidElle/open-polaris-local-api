#!/usr/bin/env python3
"""
All Polaris CUs of the account with ONE login (cloud counterpart of examples/local/multi_device.py).

CUs come from the account; PINs are not stored in the cloud, so pass them:
a default PIN for all and/or per-serial overrides.

Usage:
    python3 multi_device_cloud.py --pin 1234
    python3 multi_device_cloud.py --pin 1234 --pins SER111=4321 SER222=1111
    python3 multi_device_cloud.py --pin 1234 --turn on --heat
"""

from _common import make_parser, parse, run

from open_polaris_local_api import PolarisApiError
from open_polaris_local_api.cloud import PolarisCloudClient


async def main() -> None:
    parser = make_parser("Control every Polaris CU of the account.", device=False)
    parser.add_argument("--pin", default=None, help="Default PIN for all CUs")
    parser.add_argument("--pins", nargs="*", default=[], metavar="SERIAL=PIN", help="Per-CU PIN overrides")
    parser.add_argument("--turn", choices=["on", "off"], help="Power state to apply to every CU")
    parser.add_argument("--heat", action="store_true", help="Set heating mode on every CU")
    args = parse(parser)
    pins = {k.upper(): v for k, v in (p.split("=", 1) for p in args.pins)}

    async with PolarisCloudClient(args.email, args.password, verbose=args.verbose) as cloud:
        devices = await cloud.get_devices()
        print(f"{len(devices)} Polaris CU(s)\n")

        # One session = one rolling-token counter, so CUs are handled one after the other.
        for d in devices:
            serial = d["Serial"].upper()
            pin = pins.get(serial, args.pin)
            label = f"{d.get('PlantName')}/{d.get('Name') or serial}"
            if not pin:
                print(f"  {label}: skipped (no PIN)")
                continue
            cloud.use_device(serial, pin, d.get("Name") or "")
            try:
                dev, zones = await cloud.async_update()  # needed before CU writes
                if args.turn:
                    await (cloud.turn_on() if args.turn == "on" else cloud.turn_off())
                if args.heat:
                    await cloud.set_heating_mode()
                print(f"  {label}: {'ON' if dev.is_on else 'OFF'} {dev.cooling_mode_name}, {len(zones)} zone(s)"
                      + (" (changes queued)" if args.turn or args.heat else ""))
            except (PolarisApiError, TimeoutError) as e:
                print(f"  {label}: {type(e).__name__}: {e}")


if __name__ == "__main__":
    run(main)
