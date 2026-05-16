"""
Polaris Device Auto-Discovery

Discovers Tecnosystemi Polaris 5X CU devices on the local network via TCP
subnet scan. Each probe opens a short-lived TCP connection on port 1235
(the same transport used by PolarisLocalClient) and validates the response.
"""

import asyncio
import json
import logging
from ipaddress import IPv4Network, ip_network
from typing import Any, List, Optional, Set

_LOGGER = logging.getLogger(__name__)

_BUFFER_SIZE = 4096
_PROBE_CMD = "stato_r"


def _build_probe(pin: str) -> bytes:
    return json.dumps({"c": _PROBE_CMD, "pin": pin}).encode("utf-8")


def _is_valid_polaris_response(response: Any) -> bool:
    """Check if a TCP response looks like a Polaris CU status reply."""
    return (
        isinstance(response, dict)
        and "fw_ver" in response
        and "serial" in response
        # res=1 → success, res=4 → CMD_NOT_FOUND (old firmware, no stato_r)
        # both confirm the host is a Polaris device
        and response.get("res") in (1, 4)
    )


class PolarisAutoDiscovery:
    """
    Discovers Polaris 5X CU devices on the local network.

    Opens a short-lived TCP connection to port 1235 on every host in the
    given subnet and validates the response against the Polaris protocol.

    Usage::

        ips = await PolarisAutoDiscovery.discover(pin="1234", subnet="192.168.1.0/24")
        # ["192.168.1.42", "192.168.1.55"]
    """

    @staticmethod
    async def discover(
        pin: str,
        subnet: str,
        port: int = 1235,
        probe_timeout: float = 1.5,
        max_concurrent: int = 50,
        verbose: bool = False,
    ) -> List[str]:
        """
        Discover Polaris devices on the local network via TCP subnet scan.

        Probes every host in *subnet* concurrently (up to *max_concurrent* at
        a time) by opening a TCP connection on *port*, sending a ``stato_r``
        command, and validating the response.

        Args:
            pin: Device PIN used for the probe command.
            subnet: CIDR notation for the scan (e.g. ``"192.168.1.0/24"``).
            port: TCP port Polaris devices listen on (default 1235).
            probe_timeout: Per-host timeout in seconds (default 1.5).
            max_concurrent: Maximum simultaneous TCP probes (default 50).
            verbose: Enable debug logging.

        Returns:
            Sorted list of IP address strings of discovered devices.
        """
        probe = _build_probe(pin)
        discovered = await PolarisAutoDiscovery._subnet_scan(
            probe=probe,
            subnet=subnet,
            port=port,
            probe_timeout=probe_timeout,
            max_concurrent=max_concurrent,
            verbose=verbose,
        )
        return sorted(discovered)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _probe_host(
        ip_str: str,
        port: int,
        probe: bytes,
        timeout: float,
        verbose: bool,
    ) -> Optional[str]:
        """Open a TCP connection, send the probe, and return the IP if valid."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip_str, port),
                timeout=timeout,
            )
            try:
                writer.write(probe)
                await writer.drain()

                data = b""
                while True:
                    chunk = await asyncio.wait_for(reader.read(_BUFFER_SIZE), timeout=timeout)
                    if not chunk:
                        break
                    data += chunk
                    if len(chunk) < _BUFFER_SIZE:
                        break

                if not data:
                    return None

                response = json.loads(data.decode("utf-8"))
                if _is_valid_polaris_response(response):
                    if verbose:
                        _LOGGER.debug(
                            "✓ Discovered Polaris at %s (fw: %s, serial: %s)",
                            ip_str,
                            response.get("fw_ver", "?"),
                            response.get("serial", "?"),
                        )
                    return ip_str

            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass

        except (asyncio.TimeoutError, OSError, json.JSONDecodeError, ValueError):
            pass

        return None

    @staticmethod
    async def _subnet_scan(
        probe: bytes,
        subnet: str,
        port: int,
        probe_timeout: float,
        max_concurrent: int,
        verbose: bool,
    ) -> Set[str]:
        try:
            network = ip_network(subnet, strict=False)
        except ValueError as e:
            raise ValueError(f"Invalid subnet '{subnet}': {e}")

        if not isinstance(network, IPv4Network):
            raise ValueError(f"Only IPv4 subnets are supported, got: {subnet}")

        semaphore = asyncio.Semaphore(max_concurrent)
        discovered: Set[str] = set()

        async def scan(ip_str: str) -> None:
            async with semaphore:
                result = await PolarisAutoDiscovery._probe_host(
                    ip_str, port, probe, probe_timeout, verbose
                )
                if result is not None:
                    discovered.add(result)

        await asyncio.gather(*[scan(str(ip)) for ip in network.hosts()])
        return discovered
