"""Small async subprocess component used by DummyNet v2 infrastructure."""

import asyncio
import getpass
import os
from dataclasses import dataclass
from typing import Protocol


class SudoError(RuntimeError):
    """DummyNet could not obtain sudo privileges."""


@dataclass(frozen=True)
class ProcessResult:
    """Completed subprocess data shared between infrastructure components."""

    returncode: int
    stdout: str
    stderr: str


class Process(Protocol):
    """Command execution required by infrastructure adapters."""

    async def run(self, command: list[str], sudo: bool = False) -> ProcessResult: ...


class LocalProcess:
    """Launch local commands without a shell and capture their output.

    Sudo credentials are requested only when a privileged command is first run.
    A password can be supplied through ``DUMMYNET_SUDO_PASSWD`` for unattended
    execution; otherwise it is prompted for locally. Passwords are sent only on
    stdin and are never included in commands or results.
    """

    def __init__(self):
        self._sudo_checked = False
        self._sudo_password: str | None = None

    async def run(self, command: list[str], sudo: bool = False) -> ProcessResult:
        """Run ``command`` and return its exit status and decoded output."""

        if not sudo or os.geteuid() == 0:
            return await self._execute(command)

        await self._prepare_sudo()
        if self._sudo_password is None:
            return await self._execute(["sudo", "--non-interactive", *command])

        return await self._execute(
            ["sudo", "--stdin", *command], stdin_text=self._sudo_password
        )

    async def _prepare_sudo(self) -> None:
        if self._sudo_checked:
            return

        # Ignore cached sudo credentials for this check so behavior is explicit
        # and repeatable at the start of a DummyNet process.
        check = await self._execute(
            ["sudo", "--non-interactive", "--reset-timestamp", "true"]
        )
        if check.returncode == 0:
            self._sudo_checked = True
            return

        password = os.environ.get("DUMMYNET_SUDO_PASSWD")
        if password is None:
            prompt = f"[sudo] password for {getpass.getuser()}: "
            password = await asyncio.to_thread(getpass.getpass, prompt)
        if not password.endswith("\n"):
            password += "\n"

        validation = await self._execute(
            ["sudo", "--reset-timestamp", "--stdin", "true"],
            stdin_text=password,
        )
        if validation.returncode != 0:
            raise SudoError("Could not obtain sudo privileges")

        self._sudo_password = password
        self._sudo_checked = True

    async def _execute(
        self, command: list[str], stdin_text: str | None = None
    ) -> ProcessResult:
        # The test harness may use this variable to hand credentials to worker
        # processes, but commands launched by DummyNet must never inherit it.
        environment = os.environ.copy()
        environment.pop("DUMMYNET_SUDO_PASSWD", None)

        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE if stdin_text is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
        stdout, stderr = await process.communicate(
            None if stdin_text is None else stdin_text.encode()
        )
        return ProcessResult(
            returncode=process.returncode,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
        )
