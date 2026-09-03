"""Controller-side orchestration for starting a DummyNet runner.

Bootstrap is deliberately non-authoritative: it only ensures that a runner is
starting or active and returns its published TCP endpoint. Version checks and
session acquisition will happen over TCP in later implementation steps.

The bootstrap object is independent of concrete systemd, file, and timing
implementations. The same orchestration can therefore be used with local,
SSH-backed, or test implementations of those dependencies.
"""

import ipaddress
import json
from dataclasses import dataclass
from typing import Protocol

from .clock import Clock
from .filesystem import File
from .systemd import Systemd


class BootstrapError(RuntimeError):
    """The runner could not be bootstrapped."""


class BootstrapTimeoutError(BootstrapError):
    """The runner did not publish its endpoint in time."""


@dataclass(frozen=True)
class RunnerEndpoint:
    """Address published by a runner once it is ready for TCP connections."""

    address: str
    port: int


@dataclass(frozen=True)
class BootstrapConfig:
    """Values describing one runner bootstrap operation."""

    endpoint_file: File
    runner_command: tuple[str, ...]
    unit_name: str = "dummynet-runner.service"
    timeout: float = 30.0
    poll_interval: float = 0.1


class Bootstrap(Protocol):
    """Operation used by DummyNet to make a runner reachable."""

    async def run(self, config: BootstrapConfig) -> RunnerEndpoint: ...


class LocalBootstrap:
    """Bootstrap orchestration using injected systemd and clock components."""

    def __init__(self, systemd: Systemd, clock: Clock):
        self.systemd = systemd
        self.clock = clock

    async def run(self, config: BootstrapConfig) -> RunnerEndpoint:
        """Ensure a runner is starting or active and return its endpoint.

        The fixed systemd unit name provides host-level startup serialization.
        This method does not claim ownership of the runner or replace an active
        one.
        """

        if not await self._runner_is_available(config.unit_name):
            result = await self.systemd.run(
                config.unit_name, list(config.runner_command)
            )

            if result.returncode != 0:
                # Another bootstrap may have won the race to create the unit.
                if not await self._runner_is_available(config.unit_name):
                    detail = result.stderr.strip()
                    message = f"Could not start systemd unit {config.unit_name!r}"
                    if detail:
                        message += f": {detail}"
                    raise BootstrapError(message)

        # systemd-run returns before the runner has opened and published its
        # listening socket, so readiness must be polled separately.
        deadline = self.clock.monotonic() + config.timeout

        while True:
            if await config.endpoint_file.exists():
                text = await config.endpoint_file.read_text()
                return _parse_endpoint(text, config.endpoint_file.path)

            now = self.clock.monotonic()
            if now >= deadline:
                raise BootstrapTimeoutError(
                    f"Systemd unit {config.unit_name!r} did not publish "
                    f"{config.endpoint_file.path!r} within {config.timeout:g} seconds"
                )

            await self.clock.sleep(min(config.poll_interval, deadline - now))

    async def _runner_is_available(self, unit_name: str) -> bool:
        """Return whether systemd considers the fixed unit usable."""

        state = await self.systemd.status(unit_name)
        return state in {"activating", "active", "reloading"}


def _parse_endpoint(text: str, path: str) -> RunnerEndpoint:
    """Parse untrusted endpoint-file contents into a validated value object."""

    try:
        value = json.loads(text)
        address = value["address"]
        port = value["port"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise BootstrapError(f"Invalid runner endpoint in {path!r}") from error

    if not isinstance(address, str):
        raise BootstrapError(f"Invalid runner address in {path!r}")
    try:
        ipaddress.ip_address(address)
    except ValueError as error:
        raise BootstrapError(f"Invalid runner address in {path!r}") from error

    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise BootstrapError(f"Invalid runner port in {path!r}")

    return RunnerEndpoint(address=address, port=port)
