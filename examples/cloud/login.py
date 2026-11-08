#!/usr/bin/env python3
"""
Login only: check that the credentials work and show what the account returns.

Usage:
    python3 login.py --email me@x.com --password '...'
    POLARIS_EMAIL=me@x.com POLARIS_PASSWORD=... python3 login.py
"""

from _common import make_parser, parse, run

from open_polaris_local_api.cloud import PolarisCloudClient


async def main() -> None:
    args = parse(make_parser("Login to the Polaris cloud.", device=False))
    async with PolarisCloudClient(args.email, args.password, verbose=args.verbose) as cloud:
        print("Login OK.")
        print(f"  Plants : {len(cloud.plants)}")
        print(f"  Devices: {sum(len(p.get('ListDevices') or []) for p in cloud.plants)} (all types)")


if __name__ == "__main__":
    run(main)
