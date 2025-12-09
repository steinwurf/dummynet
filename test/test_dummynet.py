import dummynet
from dummynet import errors
from dummynet.run_info import RunInfo
from dummynet import (
    DummyNet,
    HostShell,
    ProcessMonitor,
)

import logging
import signal
import time
import os

import pytest


def test_run(net: DummyNet):
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


def test_run_strings(net: DummyNet):
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


def test_run_async(process_monitor: ProcessMonitor, net: DummyNet):
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


def test_link_vlan_ping(process_monitor: ProcessMonitor, net: DummyNet):
    """Test VLAN interface creation and connectivity with ping"""
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


def test_link_vlan_isolation(process_monitor: ProcessMonitor, net: DummyNet):
    """Test that different VLANs are isolated from each other"""
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


def test_addr_del_with_ping(process_monitor: ProcessMonitor, net: DummyNet):
    """Test that ping fails after address deletion"""
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


def test_cleanup_with_system_devices(net: DummyNet):
    net.link_veth_add("veth0", "veth1")
    net.bridge_add("br0")
    net.bridge_set("br0", "veth1")


def test_with_timeout(
    log: logging.Logger, process_monitor: ProcessMonitor, net: DummyNet
):
    # Run a command on the host
    out = net.run(cmd="ping -c 5 127.0.0.1")
    out.match(stdout="5 packets transmitted*", stderr=None)

    out = net.run_async(cmd="ping -c 5000 127.0.0.1")

    end_time = time.time() + 2

    while process_monitor.keep_running(timeout=0.5):
        if time.time() >= end_time:
            log.debug("Test timeout")
            process_monitor.stop()


def test_daemon_exit(process_monitor: ProcessMonitor, shell: DummyNet):
    # Run two commands on the host where the daemon will exit
    # before the non-daemon command
    shell.run_async(cmd="ping -c 5 127.0.0.1", daemon=True)
    shell.run_async(cmd="ping -c 50 127.0.0.1")

    with pytest.raises(ExceptionGroup) as e:
        while process_monitor.keep_running():
            pass

    assert e.group_contains(dummynet.DaemonExitError)


def test_contextmanager_netns_cleanup(net: DummyNet):
    with net as net:
        assert net.netns_list() == []

        example = net.netns_add("example")
        assert net.netns_list() == [example.namespace]
    assert net.netns_list() == []


def test_try_finally_netns_cleanup(net: DummyNet):
    try:
        assert net.netns_list() == []
        example = net.netns_add("example")
        assert net.netns_list() == [example.namespace]
    finally:
        net.cleanup()
        assert net.netns_list() == []


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


def test_link_delete_cleanup(net: DummyNet):
    assert len(net.cleaners) == 0
    veth0, _ = net.link_veth_add("veth0", "veth1")
    net.link_delete(veth0)
    assert len(net.cleaners) == 0


def test_link_delete_cleanup_naughty(net: DummyNet):
    _, veth1 = net.link_veth_add("veth0", "veth1")
    net.link_delete(veth1)
    # We don't spot that veth1 is in a veth pair with veth0 in the cleanup stage
    # for link_delete.
    assert len(net.cleaners) == 1
    # Cleanup after the test should still handle this case without throwing,
    # even if veth0 is already gone.


def test_link_delete_cleanup_evil(net: DummyNet):
    ns = net.netns_add("ns")
    net.link_veth_add("veth0", "veth1")
    net.link_set(ns, interface="veth0")
    n_cleaners = len(net.cleaners)
    ns.link_delete("veth0")
    # Should be two less. One for undoing `link_set` and one for `link_veth_add`.
    print(net.cleaners)
    assert len(net.cleaners) == (n_cleaners - 2)


def test_up_previous_state_is_kept(shell: HostShell, net: DummyNet):
    net.link_veth_add("v0", "v1")
    net.addr_add("10.10.10.10", "v0")
    net.addr_add("10.10.10.11", "v1")
    net.up("v0")
    net.up("v1")

    # Create a seperate dummynet instance to test cleanup only for its subset
    # of commands.
    with DummyNet(shell=shell) as net2:
        net2.up("v0")
        net2.up("v1")

    assert net._current_administrative_state("v0") == "up"
    assert net._current_administrative_state("v1") == "up"

    with DummyNet(shell=shell) as net2:
        net2.down("v0")
        net2.down("v1")

    assert net._current_administrative_state("v0") == "up"
    assert net._current_administrative_state("v1") == "up"


def test_down_previous_state_is_kept(shell: HostShell, net: DummyNet):
    net.link_veth_add("v0", "v1")
    net.addr_add("10.10.11.10", "v0")
    net.addr_add("10.10.11.11", "v1")

    # Create a seperate dummynet instance to test cleanup only for its subset
    # of commands.
    with DummyNet(shell=shell) as net:
        net.up("v0")
        net.up("v0")

    assert net._current_administrative_state("v0") == "down"
    assert net._current_administrative_state("v1") == "down"

    with DummyNet(shell=shell) as net:
        net.down("v0")
        net.down("v0")

    assert net._current_administrative_state("v0") == "down"
    assert net._current_administrative_state("v1") == "down"


def test_route_down_teardown(net: DummyNet):
    ns = net.netns_add("ns")

    ns.link_veth_add("v0", "v1")
    ns.addr_add("10.10.12.10", "v0")
    ns.addr_add("10.10.12.11", "v1")
    ns.up("v0")
    ns.up("v1")
    ns.shell.run("ip route")
    ns.route("10.10.12.10")
    ns.shell.run("ip route")

    # Down should only make teardown throw a warning on deleting the route.
    ns.down("v0")


def test_route_downup_teardown(net: DummyNet):
    ns = net.netns_add("ns")

    ns.link_veth_add("v0", "v1")
    ns.addr_add("10.10.12.10", "v0")
    ns.addr_add("10.10.12.11", "v1")
    ns.up("v0")
    ns.up("v1")
    ns.shell.run("ip route")
    ns.route("10.10.12.10")
    ns.shell.run("ip route")

    # Down and up should not stop the teardown from functioning.
    ns.down("v0")
    time.sleep(0.2)
    ns.up("v0")
    ns.shell.run("ip route")


def test_cleanup_daemon_death(shell: HostShell):
    net = DummyNet(shell=shell)

    demo = net.netns_add("demo")
    # A daemon should never return, oops!
    demo.shell.run_async("echo", daemon=True)
    # Allow some polls to run in the background.
    time.sleep(0.1 * 5)

    # Quickly set up a fail-and-recover cleaner
    demo.link_veth_add("v0", "v1")
    demo.addr_add("10.10.12.10", "v0")
    demo.addr_add("10.10.12.11", "v1")
    demo.up("v0")
    demo.up("v1")
    demo.route("10.10.12.10")
    # Removes route as well, causing a handled exception through cleanup.
    demo.down("v0")

    # This should raise, but also have cleaned up correctly.
    with pytest.raises(ExceptionGroup) as exception:
        net.cleanup()

    # Ensure we only got 1 DaemonExitError exception, and nothing else.
    assert exception.type is ExceptionGroup
    daemon_exceptions, other_exceptions = exception.value.split(errors.DaemonExitError)
    assert daemon_exceptions is not None and len(daemon_exceptions.exceptions) == 1
    assert other_exceptions is None

    # Ensure cleanup was successful, even when we errored.
    netns, cgroups, links = net.netns_list(), net.cgroup_list(), net.link_list()
    assert links == [], f"teardown: expected no links, found: {links!r}."
    assert cgroups == [], f"teardown: expected no cgroups, found: {cgroups!r}."
    assert netns == [], f"teardown: expected no namespaces, found: {netns!r}."


def test_stop_process_async(process_monitor: ProcessMonitor):
    daemon = process_monitor.run_process_async("sleep 100", sudo=False, daemon=True)
    process_monitor.stop_process_async(daemon)
    assert daemon.returncode is not None

    process = process_monitor.run_process_async("sleep 100", sudo=False, daemon=False)
    process_monitor.stop_process_async(process)
    assert process.returncode is not None

    fake_process = RunInfo(
        cmd="echo",
        cwd=None,
        pid=None,
        stdout=None,
        stderr=None,
        returncode=None,
        is_async=False,
        is_daemon=False,
        timeout=None,
    )
    with pytest.raises(ValueError):
        process_monitor.stop_process_async(fake_process)


def test_stop_process_async_kill(process_monitor: ProcessMonitor):
    # Clean exit will get returned correctly.
    process = process_monitor.run_process_async(
        """
        trap 'exit 0' TERM
        while :; do
            sleep 10 &
            wait $!
        done
        """,
        sudo=False,
        daemon=False,
    )
    process_monitor.stop_process_async(process)
    assert process.returncode == 0

    # Unclean SIGKILL from "hanging" process gets returned as -9 (SIGKILL).
    process = process_monitor.run_process_async(
        """
        trap '' TERM
        while :; do
            sleep 10 &
            wait $!
        done
        """,
        sudo=False,
        daemon=False,
    )
    process_monitor.stop_process_async(process)
    assert signal.Signals(-process.returncode).name == "SIGKILL"  # type: ignore

    # Daemon can also get killed and will respond to first -15 (SIGTERM) signal.
    daemon = process_monitor.run_process_async("sleep 10", sudo=False, daemon=False)
    process_monitor.stop_process_async(daemon)
    assert signal.Signals(-daemon.returncode).name == "SIGTERM"  # type: ignore


def test_cpu_usage_statistics(process_monitor: ProcessMonitor):
    def run_task_async(task, sudo, utime):
        process = process_monitor.run_process_async(task, sudo=sudo)

        while process_monitor.keep_running():
            pass

        # Allow a 5% margin of the given utime value
        margin = utime * 0.05
        assert (utime - margin) <= process.rusage.ru_utime <= (utime + margin)

    run_task_async("stress --cpu 1 --timeout 1", sudo=False, utime=1.0)
    run_task_async(["stress", "--cpu", "2", "--timeout", "1"], sudo=False, utime=2.0)
    run_task_async("stress --cpu 1 --timeout 2", sudo=True, utime=2.0)
    run_task_async(["stress", "--cpu", "2", "--timeout", "2"], sudo=True, utime=4.0)
