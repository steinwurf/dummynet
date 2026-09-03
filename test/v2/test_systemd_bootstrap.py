"""Integration test for the complete local systemd bootstrap path."""

import asyncio
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from dummynet.v2.bootstrap import BootstrapConfig, LocalBootstrap
from dummynet.v2.clock import LocalClock
from dummynet.v2.filesystem import LocalFile
from dummynet.v2.process import LocalProcess
from dummynet.v2.systemd import LocalSystemd


def systemd_is_available() -> bool:
    """Check whether this test environment has a running systemd manager."""

    if shutil.which("systemctl") is None or shutil.which("systemd-run") is None:
        return False
    if not Path("/run/systemd/system").is_dir():
        return False

    try:
        result = subprocess.run(
            ["systemctl", "show", "--property=Version", "--value"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


@pytest.mark.systemd
@pytest.mark.skipif(not systemd_is_available(), reason="systemd is not available")
def test_runner_bootstraps_and_exits_when_not_acquired(tmp_path):
    async def scenario():
        # A unique unit keeps this lifecycle test independent of parallel tests
        # and of a real dummynet-runner.service on the same machine.
        unit = f"dummynet-runner-test-{uuid.uuid4().hex}.service"
        endpoint_file = LocalFile(str(tmp_path / "endpoint.json"))
        process = LocalProcess()
        systemd = LocalSystemd(process)
        bootstrap = LocalBootstrap(systemd, LocalClock())

        runner_command = (
            sys.executable,
            "-m",
            "dummynet.v2.runner",
            "--endpoint-path",
            endpoint_file.path,
            "--idle-timeout",
            "1.0",
        )

        try:
            endpoint = await bootstrap.run(
                BootstrapConfig(
                    endpoint_file=endpoint_file,
                    runner_command=runner_command,
                    unit_name=unit,
                    timeout=5.0,
                    poll_interval=0.05,
                )
            )

            assert endpoint.address == "127.0.0.1"
            assert 1 <= endpoint.port <= 65535

            # Do not connect: this verifies the initial no-acquisition timeout.
            deadline = asyncio.get_running_loop().time() + 5.0
            while (
                await endpoint_file.exists()
                and asyncio.get_running_loop().time() < deadline
            ):
                await asyncio.sleep(0.05)

            assert not await endpoint_file.exists()

            while (
                await systemd.status(unit) in {"activating", "active", "deactivating"}
                and asyncio.get_running_loop().time() < deadline
            ):
                await asyncio.sleep(0.05)

            assert await systemd.status(unit) not in {
                "activating",
                "active",
                "deactivating",
            }
        finally:
            # Keep a failed test from leaving a privileged transient unit or
            # endpoint behind. systemctl may return non-zero if --collect has
            # already removed the completed unit, which is harmless here.
            await process.run(["systemctl", "stop", unit], sudo=True)
            await process.run(["systemctl", "reset-failed", unit], sudo=True)
            await endpoint_file.remove(missing_ok=True)

    asyncio.run(scenario())
