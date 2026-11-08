#!/usr/bin/env python3
"""
List the Polaris control units bound to the account.

The cloud does not return PINs: you need the CU PIN (set in the app) to read or control it.

Usage:
    python3 list_devices.py --email me@x.com --password '...'
    python3 list_devices.py --email me@x.com --password '...' --json
"""

import json

from _common import make_parser, parse, run

from open_polaris_local_api.cloud import PolarisCloudClient


async def main() -> None:
    parser = make_parser("List Polaris CUs on the cloud account.", device=False)
    parser.add_argument("--json", action="store_true", help="Print the raw plants JSON (all device types)")
    args = parse(parser)
    async with PolarisCloudClient(args.email, args.password, verbose=args.verbose) as cloud:
        if args.json:
            print(json.dumps(await cloud.get_plants(), indent=2))
            return
        devices = await cloud.get_devices()
        for d in devices:
            print(f"  - {d.get('Serial'):<14} plant={d.get('PlantName')!r} name={d.get('Name')!r} "
                  f"fw={d.get('FWVer')} errors={d.get('NUM_ERROR')}")
        if not devices:
            print("No Polaris CU on this account.")


if __name__ == "__main__":
    run(main)
