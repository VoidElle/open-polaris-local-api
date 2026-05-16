#!/usr/bin/env python3
"""
Auto-discovery then connect.

Scans the subnet for Polaris CU devices, prints what it finds,
then connects to each discovered device and reads its status.

Usage:
    python3 auto_discovery.py --subnet 192.168.1.0/24 --pin 1234
    python3 auto_discovery.py --subnet 192.168.1.0/24 --pin 1234 --timeout 3.0
"""

import asyncio
import argparse

from open_polaris_local_api import PolarisAutoDiscovery, PolarisLocalClient, PolarisApiError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover Polaris devices then read their status.")
    parser.add_argument("--subnet",  required=True,             help="CIDR subnet to scan (e.g. 192.168.1.0/24)")
    parser.add_argument("--pin",     required=True,             help="Device PIN (all devices must share the same PIN)")
    parser.add_argument("--timeout", type=float, default=1.5,   help="Per-host probe timeout in seconds (default: 1.5)")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    print(f"Scanning {args.subnet}…")
    ips = await PolarisAutoDiscovery.discover(
        pin=args.pin,
        subnet=args.subnet,
        probe_timeout=args.timeout,
    )

    if not ips:
        print("No Polaris devices found.")
        return

    print(f"Found {len(ips)} device(s): {', '.join(ips)}\n")

    for ip in ips:
        try:
            async with PolarisLocalClient(ip=ip, pin=args.pin) as client:
                device, zones = await client.async_update()
                print(f"[{ip}]  {device.name}  (fw: {device.fw_ver})")
                print(f"  Power : {'ON' if device.is_on else 'OFF'}")
                print(f"  Mode  : {device.cooling_mode_name}")
                print(f"  Zones : {len(zones)}")
                for zone in zones:
                    temp = f"{zone.current_temp}°C" if zone.current_temp is not None else "—"
                    print(f"    Zone {zone.zone_id} '{zone.name}': {'OFF' if zone.is_off else 'ON'}  {temp}")
                print()
        except (TimeoutError, PolarisApiError) as e:
            print(f"[{ip}] Connection failed: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
