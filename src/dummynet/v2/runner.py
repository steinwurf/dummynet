"""Minimal host-side lifecycle for the DummyNet v2 runner.

This first runner increment only opens a TCP listener, publishes its endpoint,
and exits after an idle timeout. It intentionally has no protocol or session
concept yet; those can be added without changing how bootstrap discovers it.
"""

import argparse
import asyncio
import json
import signal
from dataclasses import dataclass
from typing import Any

from .clock import Clock, LocalClock
from .filesystem import File, LocalFile


@dataclass(frozen=True)
class RunnerConfig:
    """Host-side settings supplied by the transient systemd unit."""

    address: str = "127.0.0.1"
    idle_timeout: float = 60.0


@dataclass
class RunnerContext:
    """Configuration and replaceable host facilities used by the runner.

    The network component returns an endpoint dictionary from ``listen`` and
    exposes ``close``. The endpoint file and clock use their transport-neutral
    protocols. Keeping these contracts small makes lifecycle and failure cleanup
    deterministic in tests.
    """

    config: RunnerConfig
    endpoint_file: File
    network: Any
    clock: Clock


async def run_runner(ctx: RunnerContext) -> None:
    """Publish a listening endpoint and remove it after the idle timeout.

    Cleanup also runs when the task is cancelled, which is how the executable
    handles systemd's SIGTERM during normal service shutdown.
    """

    config = ctx.config

    # Do not remove a pre-existing endpoint if publication itself fails. A later
    # startup-reconciliation step will decide how stale files are handled.
    endpoint_published = False
    try:
        endpoint = await ctx.network.listen(config.address, 0)
        await ctx.endpoint_file.write_text(json.dumps(endpoint))
        endpoint_published = True
        await ctx.clock.sleep(config.idle_timeout)
    finally:
        try:
            await ctx.network.close()
        finally:
            if endpoint_published:
                await ctx.endpoint_file.remove(missing_ok=True)


class LocalNetwork:
    """Asyncio-backed TCP listener used by the standalone runner."""

    def __init__(self):
        self._server: asyncio.Server | None = None

    async def listen(self, address: str, port: int) -> dict:
        self._server = await asyncio.start_server(self._close_connection, address, port)
        socket = self._server.sockets[0]
        bound_address, bound_port = socket.getsockname()[:2]
        return {"address": bound_address, "port": bound_port}

    async def close(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    @staticmethod
    async def _close_connection(
        _reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        # Until the runner protocol exists, connections cannot acquire a session.
        writer.close()
        await writer.wait_closed()


async def _run(config: RunnerConfig, endpoint_file: File) -> None:
    ctx = RunnerContext(
        config=config,
        endpoint_file=endpoint_file,
        network=LocalNetwork(),
        clock=LocalClock(),
    )
    task = asyncio.create_task(run_runner(ctx))
    loop = asyncio.get_running_loop()

    try:
        # Cancelling rather than immediately terminating allows run_runner's
        # finally block to close the socket and remove its endpoint file.
        loop.add_signal_handler(signal.SIGTERM, task.cancel)
        try:
            await task
        except asyncio.CancelledError:
            pass
    finally:
        loop.remove_signal_handler(signal.SIGTERM)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a minimal DummyNet runner")
    parser.add_argument("--endpoint-path", default="/run/dummynet/endpoint.json")
    parser.add_argument("--address", default="127.0.0.1")
    parser.add_argument("--idle-timeout", type=float, default=60.0)
    args = parser.parse_args()

    asyncio.run(
        _run(
            RunnerConfig(
                address=args.address,
                idle_timeout=args.idle_timeout,
            ),
            LocalFile(args.endpoint_path),
        )
    )


if __name__ == "__main__":
    main()
