#!/usr/bin/env python3
"""
Monitor a CU: poll like the official app (5 s) and print only when something changes.
Survives transient cloud errors and re-logs in by itself.

Usage:
    python3 monitor_cloud.py --email me@x.com --password '...' --serial SER123 --pin 1234
    python3 monitor_cloud.py --interval 15
"""

import asyncio
import time

from _common import make_parser, parse, run

from open_polaris_local_api import PolarisApiError
from open_polaris_local_api.cloud import PolarisAuthError, PolarisCloudClient


def snapshot(dev, zones) -> dict:
    snap = {"power": "ON" if dev.is_on else "OFF", "mode": dev.cooling_mode_name, "errors": dev.num_errors}
    for z in zones:
        snap[z.name] = (z.is_on, z.current_temp, z.set_temp)
    return snap


async def main() -> None:
    parser = make_parser("Monitor a Polaris CU over the cloud.")
    parser.add_argument("--interval", type=float, default=5, help="Poll period in seconds (default 5, as the app)")
    args = parse(parser)

    async with PolarisCloudClient(args.email, args.password, args.serial, args.pin,
                                  retry_attempts=1, verbose=args.verbose) as cloud:
        last: dict = {}
        failures = 0
        print("Monitoring. Ctrl+C to stop.")
        while True:
            try:
                snap = snapshot(*await cloud.async_update())
                failures = 0
                changes = {k: (last.get(k), v) for k, v in snap.items() if last.get(k) != v}
                if changes:
                    print(f"[{time.strftime('%H:%M:%S')}] " + ", ".join(
                        f"{k}: {a} -> {b}" if last else f"{k}={b}" for k, (a, b) in changes.items()))
                    last = snap
            except PolarisAuthError:
                raise  # bad credentials / blocked account: do not hammer the server
            except (PolarisApiError, TimeoutError) as e:
                failures += 1
                print(f"[{time.strftime('%H:%M:%S')}] poll failed ({failures}): {e}")
            await asyncio.sleep(min(args.interval * (1 + failures), 60))  # linear backoff, capped


if __name__ == "__main__":
    run(main)
