from dataclasses import dataclass, field
from functools import total_ordering
import os
import re
from typing import Any, ClassVar, Self

from dummynet.base58 import BASE58_ALPHABET, base58_to_int, int_to_base58

SCOPED_BASE58_PATTERN: re.Pattern = re.compile(
    rf"^d-(?P<uid>[{BASE58_ALPHABET}]+)-(?P<name>.+)$"
)


@total_ordering
@dataclass(frozen=True, order=False, unsafe_hash=False)
class Scoped:
    """
    Meta class to namespace devices, linux namespaces, and cgroups.

    Supports concurrent execution by namespacing names using a standard pattern.

    The naming pattern follows the format: ``{prefix}-{uid}-{name}``

    Examples:
        - ``d-XXXX-veth0`` - interface name
        - ``d-XXXX-demo0`` - namespace name
        - ``d-XXXX-limitcpu`` - cgroup name

    Where:
        - ``d`` is the DummyNet prefix
        - ``XXXX`` is the base58 encoded contents of uid, typically the process ID
        - ``name`` is the user-defined string

    :cvar SCOPED_MAX_LEN: Maximum length for scoped names
    :cvar UNSCOPED_NAMES: Special names that remain unscoped
    :cvar SCOPED_ATTR_NAME: The special attribute name to look for in ``from_any``.
    :cvar PREFIX_LEN: Length of the prefix (7 characters: "d-XXXX-")
    :cvar UID_MAX: Maximum allowed UID value (58^4 - 1, max 4 characters in base58).
    :param name: User-defined name component
    :param uid: Unique ID to namespace by, defaults to current process ID

    .. warning::
        Do not use this class directly! Please instead use one of the below subclasses
        ``InterfaceScoped``, ``NamespaceScoped``, or ``CGroupScoped``.
    """

    SCOPED_MAX_LEN: ClassVar[int] = 255
    UNSCOPED_NAMES: ClassVar[list[str]] = []
    SCOPED_ATTR_NAME: ClassVar[str]

    # 2 for "d-" prefix, 4 for uid in base58, 1 for "-"
    PREFIX_LEN: ClassVar[int] = 2 + 4 + 1
    UID_MAX: ClassVar[int] = 58**4 - 1

    name: str
    uid: int = field(
        default_factory=lambda: os.getpid(),
    )

    @classmethod
    def from_scoped(cls, name: str) -> Self:
        """Parse a scoped name string to its class representation.

        :param name: Scoped name string to parse (e.g., "d-XXXX-veth0")
        :returns: Instance of the class with parsed name and uid
        :raises ValueError: If the name is not a valid scoped name
        """
        return cls(**cls.parse_scoped(name))

    @classmethod
    def parse_scoped(cls, name: str) -> dict[str, Any]:
        match = SCOPED_BASE58_PATTERN.match(name)
        if not match:
            raise ValueError(
                f"{cls.__name__}: name='{name}' is not a valid scoped name!"
            )
        return {
            "name": match.group("name"),
            "uid": base58_to_int(match.group("uid")),
        }

    @classmethod
    def from_any(cls, any) -> Self:
        """Parse unknown input into a class instance.

        Supports multiple input types:

        - String: Attempts first to parse as a scoped name, then falls back to creating a new class
        - Object with special attribute: Extracts the scoped attribute
        - Instance of this class: Returns as-is

        :param any: Input to parse (string, object with scoped attribute, or class instance)
        :returns: Instance of the class
        :raises NotImplementedError: If the input type is not supported

        .. note::
            For parsing DummyNet instances, this method also checks for attributes
            like ``.namespace``, ``.interface``, or ``.cgroup`` depending on
            the used subclass.
        """
        if isinstance(any, str):
            try:
                return cls.from_scoped(any)
            except ValueError:
                return cls(name=any)
        # NOTE: This is for parsing DummyNet instances directly through `.namespace`.
        if hasattr(any, cls.SCOPED_ATTR_NAME):
            attr = getattr(any, cls.SCOPED_ATTR_NAME)
            if isinstance(attr, cls):
                return attr
        if isinstance(any, cls):
            return any
        raise NotImplementedError

    @property
    def scoped(self) -> str:
        """Get the scoped string representation.

        :returns: Scoped name string (e.g., "d-XXXX-name") or unscoped name
            if in UNSCOPED_NAMES or uid is 0
        """
        if self.name in self.UNSCOPED_NAMES or not self.uid:
            return self.name
        return f"d-{int_to_base58(self.uid)}-{self.name}"

    def __post_init__(self):
        # Validate name length
        # TODO: Handle unscoped names without PREFIX_LEN
        if self.uid and len(self.name) > (self.SCOPED_MAX_LEN - self.PREFIX_LEN):
            raise ValueError(
                f"{self.__class__.__name__}: name must be at most {self.SCOPED_MAX_LEN - self.PREFIX_LEN} characters, was {len(self.name)}"
            )

        # Ensure uid can can include `/proc/sys/kernel/pid_max` (2^22) in the minimum
        # base58 encoding, which here is at least 4 characters (58^4-1).
        if self.uid and not (0 <= self.uid <= self.UID_MAX):
            raise ValueError(
                f"{self.__class__.__name__}: uid must be between 1 and {self.UID_MAX}, was {self.uid}"
            )

    def __eq__(self, other: Any) -> bool:
        """Enable equality comparison with strings by comparing against name."""
        if type(other) is type(self):
            return (self.uid, self.name) == (other.uid, other.name)
        return NotImplemented

    def __lt__(self, other: Any) -> bool:
        if type(other) is type(self):
            return (self.uid, self.name) < (other.uid, other.name)
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.uid, self.name))

    def __str__(self) -> str:
        return self.scoped


class InterfaceScoped(Scoped):
    """Scoped subclass for network interfaces.

    Represents scoped network interface names with specific constraints
    for Linux network interfaces.

    :cvar SCOPED_MAX_LEN: Maximum interface name length (15 characters).
    :cvar UNSCOPED_NAMES: Names that remain unscoped (["lo"]).
    :cvar SCOPED_ATTR_NAME: Attribute name for scoping (".interface").
    """

    SCOPED_MAX_LEN = 15
    UNSCOPED_NAMES = ["lo"]
    SCOPED_ATTR_NAME = "interface"


class NamespaceScoped(Scoped):
    """Scoped subclass for Linux namespaces.

    Represents scoped Linux namespace names.

    :cvar SCOPED_MAX_LEN: Maximum namespace name length (255 characters).
    :cvar UNSCOPED_NAMES: Names that remain unscoped (["1"]).
    :cvar SCOPED_ATTR_NAME: Attribute name for scoping (".namespace").
    """

    SCOPED_MAX_LEN = 255
    UNSCOPED_NAMES = ["1"]
    SCOPED_ATTR_NAME = "namespace"


class CGroupScoped(Scoped):
    """Scoped subclass for cgroups.

    Represents scoped cgroup names for resource management.

    :cvar SCOPED_MAX_LEN: Maximum cgroup name length (255 characters).
    :cvar UNSCOPED_NAMES: Names that remain unscoped (empty list).
    :cvar SCOPED_ATTR_NAME: Attribute name for scoping (".cgroup").
    """

    SCOPED_MAX_LEN = 255
    UNSCOPED_NAMES = []
    SCOPED_ATTR_NAME = "cgroup"
