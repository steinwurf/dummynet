import re
import os
from dataclasses import dataclass
from dummynet.base58 import BASE58_ALPHABET, base58_to_int, int_to_base58

BASE58_PATTERN: re.Pattern = re.compile(
    rf"^d-(?P<pid>[{BASE58_ALPHABET}]+)-(?P<name>.+)$"
)


@dataclass(frozen=True, order=True)
class ScopedName:
    """
    >>> str(ScopedName("eth0", pid=4194304))"
    'd-NVpb-eth0'
    """

    name: str
    pid: int = os.getpid()

    # Interfaces can only be 15 characters long, and we use 7 characters.
    MAX_NAME_LEN: int = 15

    # Ensure pid is not more than `/proc/sys/kernel/pid_max` (2^22)
    MAX_PID = 2**22

    @property
    def scoped(self):
        if self.name == "lo":
            return self.name
        return f"d-{int_to_base58(self.pid)[: self.pid_len]}-{self.name[: self.usable_name_len]}"

    @property
    def pid_len(self) -> int:
        return len(int_to_base58(self.MAX_PID))

    @property
    def usable_name_len(self) -> int:
        # 2 for "d-" prefix, 1 for "-", plus the length of pid in base58
        return self.MAX_NAME_LEN - 2 - self.pid_len - 1

    def __str__(self):
        return self.scoped

    def __post_init__(self):
        assert len(self.name) <= self.MAX_NAME_LEN, (
            f"{self.__class__.__name__}: name cannot be longer than cannot be longer than {self.usable_name_len} characters"
        )
        assert self.pid <= self.MAX_PID, (
            f"{self.__class__.__name__}: pid cannot be greater than {self.MAX_PID}"
        )

    @classmethod
    def from_scoped(cls, name: str):
        match = BASE58_PATTERN.match(name)
        if not match:
            raise ValueError(
                f"{cls.__class__.__name__}: name='{name}' is not a valid scoped name!"
            )
        return cls(
            name=match.group("name"),
            pid=base58_to_int(match.group("pid")),
        )


@dataclass(frozen=True, order=True)
class InterfaceName(ScopedName):
    MAX_NAME_LEN: int = 15


@dataclass(frozen=True, order=True)
class BridgeName(ScopedName):
    MAX_NAME_LEN: int = 15


@dataclass(frozen=True, order=True)
class CGroupName(ScopedName):
    MAX_NAME_LEN: int = 255


@dataclass(frozen=True, order=True)
class NamespaceName(ScopedName):
    MAX_NAME_LEN: int = 255
