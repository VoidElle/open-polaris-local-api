#!/usr/bin/env python3
"""
Simple one-shot actions on a CU or one of its zones.

Usage:
    python3 simple_actions.py status
    python3 simple_actions.py on
    python3 simple_actions.py off
    python3 simple_actions.py heat
    python3 simple_actions.py cool 1            # 1=cooling, 2=dehumidification, 3=ventilation
    python3 simple_actions.py zone-temp 21.5 --zone 1
    python3 simple_actions.py zone-on --zone 1
    python3 simple_actions.py zone-off --zone 1

Credentials: --email --password --serial --pin (or POLARIS_* env vars).
Commands are queued by the cloud and applied by the CU later (FW < 4: up to 10 minutes).
"""

from _common import make_parser, parse, run

from open_polaris_local_api.cloud import PolarisCloudClient


def show(dev, zones) -> None:
    print(f"{'ON' if dev.is_on else 'OFF'} | {dev.cooling_mode_name} | errors {dev.active_errors}")
    for z in zones:
        print(f"  zone {z.zone_id} '{z.name}': {'ON' if z.is_on else 'OFF'} {z.current_temp}°C -> {z.set_temp}°C")


async def main() -> None:
    parser = make_parser("Simple Polaris cloud actions.")
    parser.add_argument("action", choices=["status", "on", "off", "heat", "cool", "zone-temp", "zone-on", "zone-off"])
    parser.add_argument("value", nargs="?", help="cooling mode (1-3) or temperature in °C")
    parser.add_argument("--zone", type=int, help="Zone id for zone-* actions")
    args = parse(parser)
    if args.action.startswith("zone-") and args.zone is None:
        parser.error("--zone is required for zone actions")
    if args.action in ("cool", "zone-temp") and args.value is None:
        parser.error(f"{args.action} needs a value")

    async with PolarisCloudClient(args.email, args.password, args.serial, args.pin,
                                  verbose=args.verbose) as cloud:
        if args.action == "status":
            show(cloud.device, cloud.zones)
            return
        zone = next((z for z in cloud.zones if z.zone_id == args.zone), None)
        if args.action.startswith("zone-") and zone is None:
            raise SystemExit(f"No zone {args.zone}; zones: {[z.zone_id for z in cloud.zones]}")
        match args.action:
            case "on":
                await cloud.turn_on()
            case "off":
                await cloud.turn_off()
            case "heat":
                await cloud.set_heating_mode()
            case "cool":
                await cloud.set_cooling_mode(int(args.value))
            case "zone-temp":
                await cloud.set_zone_temp(zone, float(args.value))
            case "zone-on":
                await cloud.turn_zone_on(zone)
            case "zone-off":
                await cloud.turn_zone_off(zone)
        print(f"{args.action} {args.value or ''}: queued. Current cloud state:".replace("  ", " "))
        show(*await cloud.async_update())


if __name__ == "__main__":
    run(main)
