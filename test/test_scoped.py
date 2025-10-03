import pytest

from dummynet.scoped import (
    Scoped,
    NamespaceScoped,
    InterfaceScoped,
    CGroupScoped,
)


def test_scoped_validators():
    """Model correctly raises on validation errors, such as max_length and uid size"""

    def run_test_for(cls: type[Scoped]):
        max_length = cls.SCOPED_MAX_LEN - cls.PREFIX_LEN

        # Class can handle max_length of name argument.
        cls(name="a" * max_length)

        # Class raises on name being max_length + 1.
        with pytest.raises(ValueError):
            cls(name="a" * (max_length + 1))

        # Class can handle max_pid of Linux kernel.
        with open("/proc/sys/kernel/pid_max", "r") as file:
            max_pid = int(file.read())
        cls(name="a", uid=max_pid)

        # Class raises on uid_max + 1.
        with pytest.raises(ValueError):
            cls(name="a", uid=cls.UID_MAX + 1)

        # Class raises on uid being below 0 as this is an unsigned int in the kernel.
        with pytest.raises(ValueError):
            cls(name="a", uid=-1)

        # Class leaves unscoped names unchanged when running `.scoped`.
        for unscoped_name in cls.UNSCOPED_NAMES:
            assert unscoped_name == cls(name=unscoped_name).scoped

    run_test_for(NamespaceScoped)
    run_test_for(CGroupScoped)
    run_test_for(InterfaceScoped)
