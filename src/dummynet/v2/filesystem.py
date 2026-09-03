"""Initial filesystem handles for DummyNet v2.

The protocol intentionally contains only operations needed by bootstrap and the
minimal runner. It can grow toward the public API in the design document as
those operations are implemented.
"""

import os
import uuid
from pathlib import Path
from typing import Protocol


class File(Protocol):
    """Transport-independent handle to a prospective or existing file."""

    @property
    def path(self) -> str: ...

    async def exists(self, *, timeout: float | None = 30) -> bool: ...

    async def read_text(
        self,
        *,
        encoding: str = "utf-8",
        timeout: float | None = 30,
    ) -> str: ...

    async def write_text(
        self,
        text: str,
        *,
        encoding: str = "utf-8",
        timeout: float | None = 30,
    ) -> None: ...

    async def remove(
        self,
        *,
        missing_ok: bool = False,
        timeout: float | None = 30,
    ) -> None: ...


class LocalFile:
    """File handle that performs operations on the local filesystem."""

    def __init__(self, path: str):
        self._path = path

    @property
    def path(self) -> str:
        return self._path

    async def exists(self, *, timeout: float | None = 30) -> bool:
        return Path(self.path).exists()

    async def read_text(
        self,
        *,
        encoding: str = "utf-8",
        timeout: float | None = 30,
    ) -> str:
        return Path(self.path).read_text(encoding=encoding)

    async def write_text(
        self,
        text: str,
        *,
        encoding: str = "utf-8",
        timeout: float | None = 30,
    ) -> None:
        destination = Path(self.path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(
            f".{destination.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        )

        try:
            # A same-directory rename prevents readers from seeing partial data.
            with temporary.open("w", encoding=encoding) as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    async def remove(
        self,
        *,
        missing_ok: bool = False,
        timeout: float | None = 30,
    ) -> None:
        Path(self.path).unlink(missing_ok=missing_ok)
