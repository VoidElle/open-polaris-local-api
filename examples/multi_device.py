#!/usr/bin/env python3
"""
Multi-device control.

Controls multiple Polaris CU devices concurrently.
Connects all devices at once, reads their statuses in parallel,
then sets a uniform mode across all of them.

Usage:
    python3 multi_device.py --pin 1234 --ips 192.168.1.100 192.168.1.101
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import argparse

from open_polaris_local_api import PolarisLocalClient, PolarisApiError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Control multiple Polaris CU devices concurrently.")
    parser.add_argument("--pin", required=True,          help="Shared device PIN")
    parser.add_argument("--ips", required=True, nargs="+", help="Device IP addresses")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    clients = [
        PolarisLocalClient(ip=ip, pin=args.pin, device_id=f"polaris_{i}")
        for i, ip in enumerate(args.ips)
    ]

    # Connect all devices in parallel
    await asyncio.gather(*[c.connect() for c in clients])
    print(f"Connected to {len(clients)} device(s).\n")

    try:
        # Read all statuses in parallel
        results = await asyncio.gather(
            *[c.async_update() for c in clients],
            return_exceptions=True,
        )

        print("Current status:")
        for client, result in zip(clients, results):
            if isinstance(result, Exception):
                print(f"  [{client.ip}]  ❌ {result}")
                continue
            device, zones = result
            print(
                f"  [{client.ip}]  {device.name}"
                f"  {'ON' if device.is_on else 'OFF'}"
                f"  {device.cooling_mode_name}"
                f"  {len(zones)} zone(s)"
            )

        # Turn all on and switch to heating mode concurrently
        print("\nTurning all ON and switching to heating mode…")
        await asyncio.gather(
            *[c.set_heating_mode() for c in clients],
            return_exceptions=True,
        )
        print("Done.")

    finally:
        await asyncio.gather(*[c.disconnect() for c in clients])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except PolarisApiError as e:
        print(f"Error: {e}")
