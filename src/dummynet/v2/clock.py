"""Clock abstraction used by timeout-driven DummyNet v2 components."""

import asyncio
import time
from typing import Protocol


class Clock(Protocol):
    """Time operations required by bootstrap and runner lifecycles."""

    def monotonic(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...


class LocalClock:
    """Clock backed by the local monotonic clock and asyncio event loop."""

    def monotonic(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
