#!/usr/bin/env python3
"""
Basic device control.

Connects to a single Polaris CU device, reads its current status
(device + zones), turns it on, and sets the operating mode.

Usage:
    python3 basic_control.py --ip 192.168.1.100 --pin 1234
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import argparse

from open_polaris_local_api import PolarisLocalClient, PolarisApiError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Basic Polaris CU device control.")
    parser.add_argument("--ip",  required=True, help="Device IP address")
    parser.add_argument("--pin", required=True, help="Device PIN")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    async with PolarisLocalClient(ip=args.ip, pin=args.pin) as client:
        device, zones = await client.async_update()

        print(f"Device : {device.name}  (serial: {device.serial}, fw: {device.fw_ver})")
        print(f"Power  : {'ON' if device.is_on else 'OFF'}")
        print(f"Mode   : {device.cooling_mode_name}")
        print(f"Canal  : {device.t_can}°C")
        if device.has_error:
            print(f"Errors : {device.active_errors}")
        print()

        for zone in zones:
            status = "OFF" if zone.is_off else "ON"
            temp   = f"{zone.current_temp}°C" if zone.current_temp is not None else "—"
            target = f"{zone.set_temp}°C"     if zone.set_temp     is not None else "—"
            print(f"  Zone {zone.zone_id} '{zone.name}': {status}  {temp} → {target}")
            if zone.has_error:
                print(f"    Errors: {zone.active_errors}")

        print("\nTurning on and switching to heating mode…")
        await client.set_heating_mode()
        print("Done.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (TimeoutError, PolarisApiError) as e:
        print(f"Error: {e}")
