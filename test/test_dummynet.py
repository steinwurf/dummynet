import dummynet
from dummynet import (
    DummyNet,
    HostShell,
    ProcessMonitor,
    CGroupScoped,
)

import logging
import time
import pytest
import os
import psutil


log = logging.getLogger("dummynet")
log.setLevel(logging.DEBUG)


def test_run():
    # Check if we need to run as sudo
    sudo = os.getuid() != 0

    # Create a process monitor
    process_monitor = ProcessMonitor(log=log)

    # The host shell used if we don't have a recording
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)

    # Create a mock shell which will receive the calls performed by the DummyNet
    # shell = mockshell.MockShell()
    # shell.open(recording="test/data/calls.json", shell=host_shell)

    # DummyNet wrapper that will prevent clean up from happening in playback
    # mode if an exception occurs
    with DummyNet(shell=shell) as net:
        # Get a list of the current namespaces
        namespaces = net.netns_list()
        assert namespaces == []

        # create two namespaces
        demo0 = net.netns_add("demo0")
        demo1 = net.netns_add("demo1")
        demo2 = net.netns_add("demo2")

        # Get a list of the current namespaces
        namespaces = net.netns_list()

        assert sorted(namespaces) == sorted(
            [demo0.namespace, demo1.namespace, demo2.namespace]
        )

        # Add a bridge in demo1
        br0 = demo1.bridge_add("br0")

        demo0_0, demo1_0 = net.link_veth_add("demo0_0", "demo1_0")
        demo1_1, demo2_0 = net.link_veth_add("demo1_1", "demo2_0")

        # Move the interfaces to the namespaces
        net.link_set(namespace=demo0, interface=demo0_0)
        net.link_set(namespace=demo1, interface=demo1_0)
        net.link_set(namespace=demo1, interface=demo1_1)
        net.link_set(namespace=demo2, interface=demo2_0)

        demo1.bridge_set(br0, interface=demo1_0)
        demo1.bridge_set(br0, interface=demo1_1)

        # Bind an IP-address to the two peers in the link.
        demo0.addr_add(ip="10.0.0.1/24", interface=demo0_0)
        demo2.addr_add(ip="10.0.0.2/24", interface=demo2_0)

        # Activate the interfaces.
        demo0.up(demo0_0)
        demo1.up(br0)
        demo1.up(demo1_0)
        demo1.up(demo1_1)
        demo2.up(demo2_0)

        # We will add 20 ms of delay, 1% packet loss, a queue limit of 100 packets
        # and 10 Mbit/s of bandwidth max.
        demo1.tc(demo1_0, delay=20, loss=1, limit=100, rate=10)
        demo1.tc(demo1_1, delay=20, loss=1, limit=100, rate=10)

        # Show the tc-configuration of the interfaces.
        demo1.tc_show(demo1_0)
        demo1.tc_show(demo1_0)

        out = demo0.run(cmd="ping -c 5 10.0.0.2")
        out.match(stdout="5 packets transmitted*", stderr=None)

    # Ensure cleanup happened
    namespaces = net.netns_list()
    assert namespaces == []


def test_run_strings():
    # Check if we need to run as sudo
    sudo = os.getuid() != 0

    # Create a process monitor
    process_monitor = ProcessMonitor(log=log)

    # The host shell used if we don't have a recording
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)

    # Create a mock shell which will receive the calls performed by the DummyNet
    # shell = mockshell.MockShell()
    # shell.open(recording="test/data/calls.json", shell=host_shell)

    # DummyNet wrapper that will prevent clean up from happening in playback
    # mode if an exception occurs
    net = DummyNet(shell=shell)

    try:
        # Get a list of the current namespaces
        namespaces = net.netns_list()
        assert namespaces == []

        # create two namespaces
        demo0 = net.netns_add(name="demo0")
        demo1 = net.netns_add(name="demo1")
        demo2 = net.netns_add(name="demo2")

        # Get a list of the current namespaces
        namespaces = net.netns_list()

        assert all(
            expected == actual.name
            for expected, actual in zip(
                ["demo0", "demo1", "demo2"], sorted(net.netns_list())
            )
        )

        # Add a bridge in demo1
        demo1.bridge_add(name="br0")

        net.link_veth_add(p1_name="demo0-0", p2_name="demo1-0")
        net.link_veth_add(p1_name="demo1-1", p2_name="demo2-0")

        # Move the interfaces to the namespaces
        net.link_set(namespace="demo0", interface="demo0-0")
        net.link_set(namespace="demo1", interface="demo1-0")
        net.link_set(namespace="demo1", interface="demo1-1")
        net.link_set(namespace="demo2", interface="demo2-0")

        demo1.bridge_set(bridge="br0", interface="demo1-0")
        demo1.bridge_set(bridge="br0", interface="demo1-1")

        # Bind an IP-address to the two peers in the link.
        demo0.addr_add(ip="10.0.0.1/24", interface="demo0-0")
        demo2.addr_add(ip="10.0.0.2/24", interface="demo2-0")

        # Activate the interfaces.
        demo0.up(interface="demo0-0")
        demo1.up(interface="br0")
        demo1.up(interface="demo1-0")
        demo1.up(interface="demo1-1")
        demo2.up(interface="demo2-0")

        # We will add 20 ms of delay, 1% packet loss, a queue limit of 100 packets
        # and 10 Mbit/s of bandwidth max.
        demo1.tc(interface="demo1-0", delay=20, loss=1, limit=100, rate=10)
        demo1.tc(interface="demo1-1", delay=20, loss=1, limit=100, rate=10)

        # Show the tc-configuration of the interfaces.
        demo1.tc_show(interface="demo1-0")
        demo1.tc_show(interface="demo1-0")

        out = demo0.run(cmd="ping -c 5 10.0.0.2")
        out.match(stdout="5 packets transmitted*", stderr=None)

    finally:
        # Clean up.
        net.cleanup()

    # Ensure cleanup happened
    namespaces = net.netns_list()
    assert namespaces == []


def test_run_async():
    # Check if we need to run as sudo
    sudo = os.getuid() != 0

    process_monitor = ProcessMonitor(log=log)

    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)

    net = DummyNet(shell=shell)

    try:
        # Get a list of the current namespaces
        namespaces = net.netns_list()
        assert namespaces == []

        # create two namespaces
        demo0 = net.netns_add("demo0")
        demo1 = net.netns_add("demo1")

        demo0_0, demo1_0 = net.link_veth_add("demo0-0", "demo1-0")

        # Move the interfaces to the namespaces
        net.link_set(namespace=demo0, interface=demo0_0)
        net.link_set(namespace=demo1, interface=demo1_0)

        # Bind an IP-address to the two peers in the link.
        demo0.addr_add(ip="10.0.0.1/24", interface=demo0_0)
        demo1.addr_add(ip="10.0.0.2/24", interface=demo1_0)

        # Activate the interfaces.
        demo0.up(demo0_0)
        demo1.up(demo1_0)
        demo0.up("lo")
        demo1.up("lo")

        proc0 = demo0.run_async(cmd="ping -c 5 10.0.0.2")
        proc1 = demo1.run_async(cmd="ping -c 5 10.0.0.1")

        def _proc0_stdout(data):
            print("proc0: {}".format(data))

        def _proc1_stdout(data):
            print("proc1: {}".format(data))

        proc0.stdout_callback = _proc0_stdout
        proc1.stdout_callback = _proc1_stdout

        while process_monitor.keep_running():
            pass

        proc0.match(stdout="5 packets transmitted*", stderr=None)
        proc1.match(stdout="5 packets transmitted*", stderr=None)

    finally:
        # Clean up.
        net.cleanup()

    # Ensure cleanup happened
    namespaces = net.netns_list()
    assert namespaces == []


def test_with_timeout():
    # Check if we need to run as sudo
    sudo = os.getuid() != 0

    # Create a process monitor
    process_monitor = ProcessMonitor(log=log)

    # The host shell used if we don't have a recording
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)

    # DummyNet wrapper that will prevent clean up from happening in playback
    # mode if an exception occurs
    net = DummyNet(shell=shell)

    try:
        # Run a command on the host
        out = net.run(cmd="ping -c 5 127.0.0.1")
        out.match(stdout="5 packets transmitted*", stderr=None)

        out = net.run_async(cmd="ping -c 5000 127.0.0.1")

        end_time = time.time() + 2

        while process_monitor.keep_running(timeout=0.5):
            if time.time() >= end_time:
                log.debug("Test timeout")
                process_monitor.stop()

    finally:
        # Clean up.
        net.cleanup()


def test_daemon_exit():
    # Check if we need to run as sudo
    sudo = os.getuid() != 0

    # Create a process monitor
    process_monitor = ProcessMonitor(log=log)

    # The host shell used if we don't have a recording
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)

    # Run two commands on the host where the daemon will exit
    # before the non-daemon command
    shell.run_async(cmd="ping -c 5 127.0.0.1", daemon=True)
    shell.run_async(cmd="ping -c 50 127.0.0.1")

    with pytest.raises(ExceptionGroup) as e:
        while process_monitor.keep_running():
            pass

    assert e.group_contains(dummynet.DaemonExitError)


def test_contextmanager_cleanup():
    sudo = os.getuid() != 0
    process_monitor = ProcessMonitor(log=log)
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)

    with DummyNet(shell=shell) as net:
        assert net.netns_list() == []

        example = net.netns_add("example")
        assert net.netns_list() == [example.namespace]

    try:
        net = DummyNet(shell=shell)
        assert net.netns_list() == []
    finally:
        net.cleanup()


def test_all_daemons():
    # Check if we need to run as sudo
    sudo = os.getuid() != 0

    # Create a process monitor
    process_monitor = ProcessMonitor(log=log)

    # The host shell used if we don't have a recording
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)

    # Run two commands where both are daemons
    shell.run_async(cmd="ping -c 5 8.8.8.8", daemon=True)
    shell.run_async(cmd="ping -c 50 8.8.8.8", daemon=True)

    with pytest.raises(dummynet.NoProcessesError):
        while process_monitor.keep_running():
            pass


def test_no_processes():
    # Create a process monitor
    process_monitor = ProcessMonitor(log=log)

    # Nothing to do
    while process_monitor.keep_running():
        pass


def test_hostshell_timeout():
    # Create a process monitor
    process_monitor = ProcessMonitor(log=log)

    # The host shell
    shell = HostShell(log=log, sudo=False, process_monitor=process_monitor)

    start = time.time()
    # Check that we get a timeout if we run a command that takes too long
    with pytest.raises(dummynet.TimeoutError):
        # Run a command on the host
        shell.run(cmd="sleep 10", timeout=1.5)

    difference = time.time() - start

    # Check that the timeout was more than 1 second but less than 2 seconds
    assert difference > 1 and difference < 2

    # Check that we don't get a timeout if we run that runs within the timeout
    shell.run(cmd="sleep 1", timeout=1.5)

    # Nothing to do
    while process_monitor.keep_running():
        pass


def _hostshell_timeout_daemon():
    # Seperated this in to a function to look like a typical integration
    # test

    # Check if we need to run as sudo
    sudo = os.getuid() != 0

    # Create a process monitor
    process_monitor = ProcessMonitor(log=log)

    # The host shell
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)

    # Start a deamon process (those should not exit before the test is over)
    shell.run_async(cmd="sleep 2", daemon=True)

    # Next we run a blocking command that will timeout
    # we expect to also be notified that the daemon process exited
    # prematurely

    shell.run(cmd="sleep 10", timeout=5)

    # Nothing to do
    while process_monitor.keep_running():
        pass


def test_hostshell_timeout_daemon():
    # Check that we get a timeout if we run a command that takes too long

    with pytest.raises(ExceptionGroup) as e:
        _hostshell_timeout_daemon()

    assert e.group_contains(dummynet.TimeoutError)
    assert e.group_contains(dummynet.DaemonExitError)


def test_run_stdout():
    # Create a process monitor
    process_monitor = ProcessMonitor(log=log)

    # The host shell used if we don't have a recording
    shell = HostShell(log=log, sudo=False, process_monitor=process_monitor)
    message = "Hello World"
    info = shell.run(cmd=f"echo '{message}'")

    assert len(info.stdout) == len(message) + 1
    assert info.stdout == f"{message}\n"

    long_message = "A" * 4096

    info = shell.run(cmd=f"echo '{long_message}'")

    assert len(info.stdout) == 4096 + 1
    assert info.stdout == f"{long_message}\n"

    very_long_message = "A" * 4096 * 10

    info = shell.run(cmd=f"echo '{very_long_message}'")

    assert len(info.stdout) == 4096 * 10 + 1
    assert info.stdout == f"{very_long_message}\n"

    # check timeout of function with a long message
    with pytest.raises(dummynet.TimeoutError):
        shell.run(cmd=f"sleep 10; echo '{very_long_message}'", timeout=1)


def test_run_async_output():
    process_monitor = ProcessMonitor(log=log)

    shell = HostShell(log=log, sudo=False, process_monitor=process_monitor)

    out1 = shell.run_async(cmd="ping -i 0.1 -c 5 127.0.0.1")
    out2 = shell.run_async(cmd="ping -i 0.1 -c 3 127.0.0.1")

    out1.stdout_callback = lambda data: print("stdout1: {}".format(data))
    out2.stdout_callback = lambda data: print("stdout2: {}".format(data))

    while process_monitor.keep_running():
        pass

    out1.match(stdout="5 packets transmitted*", stderr=None)
    out2.match(stdout="3 packets transmitted*", stderr=None)


def test_cgroup_init_and_delete():
    sudo = os.getuid() != 0

    process_monitor = ProcessMonitor(log=log)
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)
    net = DummyNet(shell=shell)
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


def test_cgroup_init_wrong_pid():
    sudo = os.getuid() != 0

    process_monitor = ProcessMonitor(log=log)
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)
    net = DummyNet(shell=shell)

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


def test_cgroup_wrong_cpu_limit():
    sudo = os.getuid() != 0

    process_monitor = ProcessMonitor(log=log)
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)
    net = DummyNet(shell=shell)

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


def test_cgroup_wrong_memory_limit():
    sudo = os.getuid() != 0

    process_monitor = ProcessMonitor(log=log)
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)
    net = DummyNet(shell=shell)

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
