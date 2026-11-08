"""Shared helpers for the cloud examples: import paths, credentials, logging."""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def make_parser(description: str, device: bool = True) -> argparse.ArgumentParser:
    """Credentials come from flags or POLARIS_EMAIL / POLARIS_PASSWORD / POLARIS_SERIAL / POLARIS_PIN."""
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--email", default=os.environ.get("POLARIS_EMAIL"), help="Account email (or POLARIS_EMAIL)")
    p.add_argument("--password", default=os.environ.get("POLARIS_PASSWORD"),
                   help="Account password (or POLARIS_PASSWORD)")
    if device:
        p.add_argument("--serial", default=os.environ.get("POLARIS_SERIAL"), help="CU serial (or POLARIS_SERIAL)")
        p.add_argument("--pin", default=os.environ.get("POLARIS_PIN"), help="CU PIN (or POLARIS_PIN)")
    p.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")
    return p


def parse(parser: argparse.ArgumentParser) -> argparse.Namespace:
    args = parser.parse_args()
    # serial/pin are required only for single-device scripts (make_parser(device=True) adds --serial);
    # multi_device_cloud adds its own optional --pin.
    required = ("email", "password") + (("serial", "pin") if "serial" in args else ())
    missing = [k for k in required if not getattr(args, k)]
    if missing:
        parser.error("missing: " + ", ".join("--" + m for m in missing))
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")
    return args


def run(main) -> None:
    import asyncio
    from open_polaris_local_api import PolarisApiError
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
    except (PolarisApiError, TimeoutError) as e:  # PolarisAuthError derives from PolarisApiError
        print(f"Error: {type(e).__name__}: {e}")
