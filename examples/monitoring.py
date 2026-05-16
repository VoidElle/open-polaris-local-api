#!/usr/bin/env python3
"""
Device monitoring.

Continuously polls a Polaris CU device and prints a status report.
Prints an alert if CU or zone errors are detected.

Usage:
    python3 monitoring.py --ip 192.168.1.100 --pin 1234
    python3 monitoring.py --ip 192.168.1.100 --pin 1234 --interval 10
"""

import asyncio
import argparse
from datetime import datetime

from open_polaris_local_api import PolarisLocalClient, PolarisApiError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Continuously monitor a Polaris CU device.")
    parser.add_argument("--ip",       required=True,          help="Device IP address")
    parser.add_argument("--pin",      required=True,          help="Device PIN")
    parser.add_argument("--interval", type=int, default=30,   help="Polling interval in seconds (default: 30)")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    print(f"Monitoring {args.ip} every {args.interval}s. Press Ctrl+C to stop.\n")

    async with PolarisLocalClient(ip=args.ip, pin=args.pin) as client:
        while True:
            try:
                device, zones = await client.async_update()
                now = datetime.now().strftime("%H:%M:%S")

                health = "✅ Healthy" if not device.has_error else "⚠️  Errors"
                power  = "🟢 ON"     if device.is_on          else "🔴 OFF"

                print(f"[{now}]  {health}  {power}")
                print(f"  Device : {device.name}  (fw: {device.fw_ver})")
                print(f"  Mode   : {device.cooling_mode_name}")
                print(f"  Canal  : {device.t_can}°C")

                if device.has_error:
                    print(f"  ❌ CU errors: {device.active_errors}")

                for zone in zones:
                    temp   = f"{zone.current_temp}°C" if zone.current_temp is not None else "—"
                    target = f"{zone.set_temp}°C"     if zone.set_temp     is not None else "—"
                    status = "OFF" if zone.is_off else "ON"
                    print(f"  Zone {zone.zone_id} '{zone.name}': {status}  {temp} → {target}")
                    if zone.has_error:
                        print(f"    ❌ Zone errors: {zone.active_errors}")

                print()

            except TimeoutError:
                now = datetime.now().strftime("%H:%M:%S")
                print(f"[{now}]  ⚠️  Timeout — retrying next interval\n")

            await asyncio.sleep(args.interval)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
    except PolarisApiError as e:
        print(f"Connection error: {e}")
