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


def test_run(net: DummyNet):
    with net as net:
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


def test_run_strings(net: DummyNet):
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


def test_run_async(process_monitor: ProcessMonitor, net: DummyNet):
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


def test_link_vlan_ping(process_monitor: ProcessMonitor, net: DummyNet):
    """Test VLAN interface creation and connectivity with ping"""
    try:
        # Create two namespaces
        demo0 = net.netns_add("demo0")
        demo1 = net.netns_add("demo1")

        # Create veth pair
        demo0_veth0, demo1_veth0 = net.link_veth_add("d0v0", "d1v0")

        # Move the interfaces to the namespaces
        net.link_set(namespace=demo0, interface=demo0_veth0)
        net.link_set(namespace=demo1, interface=demo1_veth0)

        # Create VLAN interfaces on both sides (VLAN ID 200)
        demo0_vlan = demo0.link_vlan_add(demo0_veth0, vlan_id=200)
        demo1_vlan = demo1.link_vlan_add(demo1_veth0, vlan_id=200)

        # Bind IP addresses to the VLAN interfaces
        demo0.addr_add(ip="10.0.200.1/24", interface=demo0_vlan)
        demo1.addr_add(ip="10.0.200.2/24", interface=demo1_vlan)

        # Bring up the physical interfaces
        demo0.up(demo0_veth0)
        demo1.up(demo1_veth0)

        # Bring up the VLAN interfaces
        demo0.up(demo0_vlan)
        demo1.up(demo1_vlan)

        # Bring up loopback interfaces
        demo0.up("lo")
        demo1.up("lo")

        # Run ping tests
        proc0 = demo0.run_async(cmd="ping -c 5 10.0.200.2")
        proc1 = demo1.run_async(cmd="ping -c 5 10.0.200.1")

        def _proc0_stdout(data):
            print("demo0 (VLAN 200): {}".format(data))

        def _proc1_stdout(data):
            print("demo1 (VLAN 200): {}".format(data))

        proc0.stdout_callback = _proc0_stdout
        proc1.stdout_callback = _proc1_stdout

        while process_monitor.keep_running():
            pass

        # Verify successful ping
        proc0.match(stdout="5 packets transmitted*", stderr=None)
        proc1.match(stdout="5 packets transmitted*", stderr=None)

    finally:
        # Clean up
        net.cleanup()


def test_link_vlan_isolation(process_monitor: ProcessMonitor, net: DummyNet):
    """Test that different VLANs are isolated from each other"""
    try:
        # Create two namespaces
        demo0 = net.netns_add("demo0")
        demo1 = net.netns_add("demo1")

        # Create veth pair
        demo0_veth0, demo1_veth0 = net.link_veth_add("d0v0", "d1v0")

        # Move the interfaces to the namespaces
        net.link_set(namespace=demo0, interface=demo0_veth0)
        net.link_set(namespace=demo1, interface=demo1_veth0)

        # Create different VLAN interfaces (100 vs 200)
        demo0_vlan = demo0.link_vlan_add(demo0_veth0, vlan_id=100)
        demo1_vlan = demo1.link_vlan_add(demo1_veth0, vlan_id=200)

        # Bind IP addresses to the VLAN interfaces
        demo0.addr_add(ip="10.0.100.1/24", interface=demo0_vlan)
        demo1.addr_add(ip="10.0.100.2/24", interface=demo1_vlan)

        # Bring up all interfaces
        demo0.up(demo0_veth0)
        demo1.up(demo1_veth0)
        demo0.up(demo0_vlan)
        demo1.up(demo1_vlan)
        demo0.up("lo")
        demo1.up("lo")

        # Try to ping - should fail because VLANs are different
        proc0 = demo0.run_async(
            cmd=r"""
            ping -c 3 -W 1 10.0.0.2; \
            if [ "$?" -ne 1 ]; then \
                exit 1; \
            fi
            """
        )

        def _proc0_stdout(data):
            print("demo0 (VLAN 100 -> VLAN 200): {}".format(data))

        proc0.stdout_callback = _proc0_stdout

        while process_monitor.keep_running():
            pass

        # Verify ping fails (0 packets received)
        proc0.match(stdout="*0 received*", stderr=None)

    finally:
        # Clean up
        net.cleanup()


def test_addr_del_with_ping(process_monitor: ProcessMonitor, net: DummyNet):
    """Test that ping fails after address deletion"""
    try:
        # Create two namespaces
        demo0 = net.netns_add("demo0")
        demo1 = net.netns_add("demo1")

        # Create veth pair
        demo0_veth0, demo1_veth0 = net.link_veth_add("d0v0", "d1v0")

        # Move the interfaces to the namespaces
        net.link_set(namespace=demo0, interface=demo0_veth0)
        net.link_set(namespace=demo1, interface=demo1_veth0)

        # Bind IP addresses
        demo0.addr_add(ip="10.0.0.1/24", interface=demo0_veth0)
        demo1.addr_add(ip="10.0.0.2/24", interface=demo1_veth0)

        # Bring up interfaces
        demo0.up(demo0_veth0)
        demo1.up(demo1_veth0)
        demo0.up("lo")
        demo1.up("lo")

        # First ping should succeed
        proc0 = demo0.run_async(cmd="ping -c 3 10.0.0.2")

        def _proc0_stdout(data):
            print("demo0 (before addr_del): {}".format(data))

        proc0.stdout_callback = _proc0_stdout

        while process_monitor.keep_running():
            pass

        proc0.match(stdout="3 packets transmitted*", stderr=None)

        # Now delete the address from demo1
        demo1.addr_del(ip="10.0.0.2/24", interface=demo1_veth0)

        # Second ping should fail
        proc1 = demo0.run_async(
            cmd=r"""
            ping -c 3 -W 1 10.0.0.2; \
            if [ "$?" -ne 1 ]; then \
                exit 1; \
            fi
            """
        )

        def _proc1_stdout(data):
            print("demo0 (after addr_del): {}".format(data))

        proc1.stdout_callback = _proc1_stdout

        while process_monitor.keep_running():
            pass

        # Verify ping fails
        proc1.match(stdout="*0 received*", stderr=None)

    finally:
        # Clean up
        net.cleanup()


def test_cleanup_with_system_devices(net: DummyNet):
    try:
        net.link_veth_add("veth0", "veth1")
        net.bridge_add("br0")
        net.bridge_set("br0", "veth1")
    finally:
        net.cleanup()


def test_with_timeout(process_monitor: ProcessMonitor, net: DummyNet):
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


def test_daemon_exit(process_monitor: ProcessMonitor, shell: DummyNet):
    # Run two commands on the host where the daemon will exit
    # before the non-daemon command
    shell.run_async(cmd="ping -c 5 127.0.0.1", daemon=True)
    shell.run_async(cmd="ping -c 50 127.0.0.1")

    with pytest.raises(ExceptionGroup) as e:
        while process_monitor.keep_running():
            pass

    assert e.group_contains(dummynet.DaemonExitError)


def test_contextmanager_cleanup(net: DummyNet):
    with net as net:
        assert net.netns_list() == []

        example = net.netns_add("example")
        assert net.netns_list() == [example.namespace]

    try:
        assert net.netns_list() == []
    finally:
        net.cleanup()


def test_all_daemons(process_monitor: ProcessMonitor, shell: HostShell):
    # Run two commands where both are daemons
    shell.run_async(cmd="ping -c 5 8.8.8.8", daemon=True)
    shell.run_async(cmd="ping -c 50 8.8.8.8", daemon=True)

    with pytest.raises(dummynet.NoProcessesError):
        while process_monitor.keep_running():
            pass


def test_no_processes(process_monitor: ProcessMonitor):
    # Nothing to do
    while process_monitor.keep_running():
        pass


def test_hostshell_timeout(process_monitor: ProcessMonitor, shell: HostShell):
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


def test_hostshell_timeout_daemon(process_monitor: ProcessMonitor, shell: HostShell):
    # Check that we get a timeout if we run a command that takes too long
    def hostshell_timeout_daemon():
        # Seperated this in to a function to look like a typical integration
        # test

        # Start a deamon process (those should not exit before the test is over)
        shell.run_async(cmd="sleep 2", daemon=True)

        # Next we run a blocking command that will timeout
        # we expect to also be notified that the daemon process exited
        # prematurely

        shell.run(cmd="sleep 10", timeout=5)

        # Nothing to do
        while process_monitor.keep_running():
            pass

    with pytest.raises(ExceptionGroup) as e:
        hostshell_timeout_daemon()

    assert e.group_contains(dummynet.TimeoutError)
    assert e.group_contains(dummynet.DaemonExitError)


def test_run_stdout(shell: HostShell):
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


def test_run_async_output(process_monitor: ProcessMonitor, shell: HostShell):
    out1 = shell.run_async(cmd="ping -i 0.1 -c 5 127.0.0.1")
    out2 = shell.run_async(cmd="ping -i 0.1 -c 3 127.0.0.1")

    out1.stdout_callback = lambda data: print("stdout1: {}".format(data))
    out2.stdout_callback = lambda data: print("stdout2: {}".format(data))

    while process_monitor.keep_running():
        pass

    out1.match(stdout="5 packets transmitted*", stderr=None)
    out2.match(stdout="3 packets transmitted*", stderr=None)


def test_cgroup_init_and_delete(shell: HostShell, net: DummyNet):
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


def test_cgroup_init_wrong_pid(shell: HostShell, net: DummyNet):
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


def test_cgroup_wrong_cpu_limit(shell: HostShell, net: DummyNet):
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


def test_cgroup_wrong_memory_limit(shell: HostShell, net: DummyNet):
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
