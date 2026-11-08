#!/usr/bin/env python3
"""
Basic cloud control (cloud counterpart of examples/local/basic_control.py).

Reads the CU and its zones, then turns the CU on in heating mode.
Commands are queued by the cloud: the next poll shows the result (FW < 4: up to 10 minutes).

Usage:
    python3 basic_cloud.py --email me@x.com --password '...' --serial SER123 --pin 1234
"""

from _common import make_parser, parse, run

from open_polaris_local_api.cloud import PolarisCloudClient


async def main() -> None:
    args = parse(make_parser("Basic Polaris cloud control."))
    async with PolarisCloudClient(args.email, args.password, args.serial, args.pin,
                                  verbose=args.verbose) as cloud:
        dev = cloud.device
        print(f"CU '{dev.name}' ({dev.serial}, fw {dev.fw_ver}, LAN IP {dev.ip or '?'})")
        print(f"  Power: {'ON' if dev.is_on else 'OFF'}  Mode: {dev.cooling_mode_name}  Errors: {dev.active_errors}")
        for z in cloud.zones:
            print(f"  Zone {z.zone_id} '{z.name}': {'ON' if z.is_on else 'OFF'} {z.current_temp}°C -> {z.set_temp}°C")
        await cloud.set_heating_mode()
        print("Heating mode queued.")


if __name__ == "__main__":
    run(main)
