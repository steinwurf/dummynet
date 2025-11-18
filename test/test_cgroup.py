from dummynet import (
    DummyNet,
    HostShell,
    CGroupScoped,
)

import logging
import pytest
import os
import psutil


def test_cgroup_init_and_delete(log: logging.Logger, shell: HostShell, net: DummyNet):
    try:
        cgroup = net.add_cgroup(
            name="test_cgr",
            shell=shell,
            log=log,
            cpu_limit=0.5,
            memory_limit=200000000,
        )
        cgroup.add_pid(pid=os.getpid())

        groups = shell.run(cmd="ls /sys/fs/cgroup").stdout.splitlines()
        assert cgroup.name in groups
    finally:
        net.cleanup()

    groups = shell.run(cmd="ls /sys/fs/cgroup").stdout.splitlines()
    assert cgroup.name not in groups


def test_cgroup_init_wrong_pid(log: logging.Logger, shell: HostShell, net: DummyNet):
    with pytest.raises(AssertionError) as e:
        cgroup = net.add_cgroup(
            name="test_cgroup_negative_pid",
            shell=shell,
            log=log,
            cpu_limit=0.5,
            memory_limit=200000000,
        )

        cgroup.add_pid(pid=-1)

        assert "PID must be greater than 0." in str(e)

    net.cleanup()
    groups = shell.run(cmd="ls /sys/fs/cgroup").stdout.splitlines()
    assert CGroupScoped(name="test_cgroup_negative_pid").scoped not in groups

    with pytest.raises(ProcessLookupError) as e:
        cgroup = net.add_cgroup(
            name="test_cgroup_non_pid",
            shell=shell,
            log=log,
            cpu_limit=0.5,
            memory_limit=200000000,
        )
        cgroup.add_pid(pid=999999999)

        assert "No such process" in str(e)

    net.cleanup()
    groups = shell.run(cmd="ls /sys/fs/cgroup").stdout.splitlines()
    assert CGroupScoped(name="test_cgroup_non_pid").scoped not in groups


def test_cgroup_wrong_cpu_limit(log: logging.Logger, shell: HostShell, net: DummyNet):
    with pytest.raises(AssertionError) as e:
        cgroup = net.add_cgroup(
            name="test_cgroup_wrong_cpu_limit",
            shell=shell,
            log=log,
            cpu_limit=2,
        )

        cgroup.add_pid(pid=os.getpid())

        assert "CPU limit must be in range (0, 1]." in str(e)

    groups = shell.run(cmd="ls /sys/fs/cgroup").stdout.splitlines()
    assert CGroupScoped(name="test_cgroup_wrong_cpu_limit").scoped not in groups

    with pytest.raises(AssertionError) as e:
        cgroup = net.add_cgroup(
            name="test_cgroup_wrong_cpu_limit",
            shell=shell,
            log=log,
            cpu_limit=0,
        )
        cgroup.add_pid(pid=os.getpid())

        assert "CPU limit must be in range (0, 1]." in str(e)

    groups = shell.run(cmd="ls /sys/fs/cgroup").stdout.splitlines()
    assert CGroupScoped(name="test_cgroup_wrong_cpu_limit").scoped not in groups

    with pytest.raises(AssertionError) as e:
        cgroup = net.add_cgroup(
            name="test_cgroup_wrong_cpu_limit",
            shell=shell,
            log=log,
            cpu_limit=-1,
        )
        cgroup.add_pid(pid=os.getpid())
        assert "CPU limit must be in range (0, 1]." in str(e)

    groups = shell.run(cmd="ls /sys/fs/cgroup").stdout.splitlines()
    assert CGroupScoped(name="test_cgroup_wrong_cpu_limit").scoped not in groups


def test_cgroup_wrong_memory_limit(
    log: logging.Logger, shell: HostShell, net: DummyNet
):
    with pytest.raises(AssertionError) as e:
        cgroup = net.add_cgroup(
            name="test_cgroup_wrong_memory_limit",
            shell=shell,
            log=log,
            cpu_limit=0.5,
            memory_limit=-1,
        )

        cgroup.add_pid(pid=os.getpid())

        assert "Memory limit must be in range [0, max]." in str(e)

    groups = shell.run(cmd="ls /sys/fs/cgroup").stdout.splitlines()
    assert CGroupScoped(name="test_cgroup_wrong_memory_limit").scoped not in groups

    with pytest.raises(AssertionError) as e:
        cgroup = net.add_cgroup(
            name="test_cgroup_wrong_memory_limit",
            shell=shell,
            log=log,
            cpu_limit=0.5,
            memory_limit=psutil.virtual_memory().total + 1,
        )
        cgroup.add_pid(pid=os.getpid())
        assert "Memory limit must be in range [0, max]." in str(e)

    groups = shell.run(cmd="ls /sys/fs/cgroup").stdout.splitlines()
    assert CGroupScoped(name="test_cgroup_wrong_memory_limit").scoped not in groups
