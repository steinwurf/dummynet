"""Systemd command adapter for DummyNet v2 bootstrap."""

from typing import Protocol

from .process import Process, ProcessResult


class Systemd(Protocol):
    """Systemd operations required to make a runner reachable."""

    async def status(self, unit: str) -> str: ...

    async def run(self, unit: str, command: list[str]) -> ProcessResult: ...


class LocalSystemd:
    """Translate systemd operations into commands run by a local process."""

    def __init__(self, process: Process):
        self.process = process

    async def status(self, unit: str) -> str:
        """Return the unit's ``ActiveState`` value reported by systemd."""

        result = await self.process.run(
            [
                "systemctl",
                "show",
                "--property=ActiveState",
                "--value",
                unit,
            ],
            sudo=True,
        )
        return result.stdout.strip()

    async def run(self, unit: str, command: list[str]) -> ProcessResult:
        """Start ``command`` as a collected transient service named ``unit``."""

        return await self.process.run(
            [
                "systemd-run",
                f"--unit={unit}",
                "--collect",
                "--service-type=exec",
                "--property=Restart=no",
                *command,
            ],
            sudo=True,
        )
