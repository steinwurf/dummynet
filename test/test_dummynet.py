from dummynet import DummyNet
from dummynet import HostShell
from dummynet import ProcessMonitor

import dummynet

import logging
import time
import pytest
import os

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

        assert namespaces == sorted(["demo2", "demo1", "demo0"])

        # Add a bridge in demo1
        demo1.bridge_add(name="br0")

        net.link_veth_add(p1_name="demo0-eth0", p2_name="demo1-eth0")
        net.link_veth_add(p1_name="demo1-eth1", p2_name="demo2-eth0")

        # Move the interfaces to the namespaces
        net.link_set(namespace="demo0", interface="demo0-eth0")
        net.link_set(namespace="demo1", interface="demo1-eth0")
        net.link_set(namespace="demo1", interface="demo1-eth1")
        net.link_set(namespace="demo2", interface="demo2-eth0")

        demo1.bridge_set(name="br0", interface="demo1-eth0")
        demo1.bridge_set(name="br0", interface="demo1-eth1")

        # Bind an IP-address to the two peers in the link.
        demo0.addr_add(ip="10.0.0.1/24", interface="demo0-eth0")
        demo2.addr_add(ip="10.0.0.2/24", interface="demo2-eth0")

        # Activate the interfaces.
        demo0.up(interface="demo0-eth0")
        demo1.up(interface="br0")
        demo1.up(interface="demo1-eth0")
        demo1.up(interface="demo1-eth1")
        demo2.up(interface="demo2-eth0")

        # We will add 20 ms of delay, 1% packet loss, a queue limit of 100 packets
        # and 10 Mbit/s of bandwidth max.
        demo1.tc(interface="demo1-eth0", delay=20, loss=1, limit=100, rate=10)
        demo1.tc(interface="demo1-eth1", delay=20, loss=1, limit=100, rate=10)

        # Show the tc-configuration of the interfaces.
        demo1.tc_show(interface="demo1-eth0")
        demo1.tc_show(interface="demo1-eth0")

        out = demo0.run(cmd="ping -c 10 10.0.0.2")
        out.match(stdout="10 packets transmitted*", stderr=None)

    finally:
        # Clean up.
        net.cleanup()


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
        demo0 = net.netns_add(name="demo0")
        demo1 = net.netns_add(name="demo1")

        net.link_veth_add(p1_name="demo0-eth0", p2_name="demo1-eth0")

        # Move the interfaces to the namespaces
        net.link_set(namespace="demo0", interface="demo0-eth0")
        net.link_set(namespace="demo1", interface="demo1-eth0")

        # Bind an IP-address to the two peers in the link.
        demo0.addr_add(ip="10.0.0.1/24", interface="demo0-eth0")
        demo1.addr_add(ip="10.0.0.2/24", interface="demo1-eth0")

        # Activate the interfaces.
        demo0.up(interface="demo0-eth0")
        demo1.up(interface="demo1-eth0")
        demo0.up(interface="lo")
        demo1.up(interface="lo")

        proc0 = demo0.run_async(cmd="ping -c 10 10.0.0.2")
        proc1 = demo1.run_async(cmd="ping -c 10 10.0.0.1")

        def _proc0_stdout(data):
            print("proc0: {}".format(data))

        def _proc1_stdout(data):
            print("proc1: {}".format(data))

        proc0.stdout_callback = _proc0_stdout
        proc1.stdout_callback = _proc1_stdout

        while process_monitor.keep_running():
            pass

        proc0.match(stdout="10 packets transmitted*", stderr=None)
        proc1.match(stdout="10 packets transmitted*", stderr=None)

    finally:
        # Clean up.
        net.cleanup()


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
        out = net.run(cmd="ping -c 5 8.8.8.8")
        out.match(stdout="5 packets transmitted*", stderr=None)

        out = net.run_async(cmd="ping -c 5000 8.8.8.8")

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
    shell.run_async(cmd="ping -c 5 8.8.8.8", daemon=True)
    shell.run_async(cmd="ping -c 50 8.8.8.8")

    with pytest.raises(ExceptionGroup) as e:
        while process_monitor.keep_running():
            pass

    assert e.group_contains(dummynet.DaemonExitError)


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


# @todo re-enable this test
# @pytest.fixture
# def sad_path():

#     # Check if we need to run as sudo
#     sudo = os.getuid() != 0

#     process_monitor = ProcessMonitor(log=log)
#     shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)
#     net = DummyNet(shell=shell)

#     sad_cgroup = net.add_cgroup(
#         name="test_cgroup_sad",
#         shell=shell,
#         log=log,
#         default_path="/sys/fs/cgroup",
#         controllers={"cpu.wrongname": 0, "memory.high": -200000000},
#         pid=12345,
#     )
#     return sad_cgroup


# @pytest.fixture
# def happy_path():

#     # Check if we need to run as sudo
#     sudo = os.getuid() != 0

#     process_monitor = ProcessMonitor(log=log)
#     shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)
#     net = DummyNet(shell=shell)

#     happy_cgroup = net.add_cgroup(
#         name="test_cgroup_happy",
#         shell=shell,
#         log=log,
#         default_path="/sys/fs/cgroup",
#         controllers={"cpu.max": 0.5, "memory.high": 200000000},
#         pid=os.getpid(),
#     )
#     return happy_cgroup

# def test_cgroup_build(happy_path):
#     cgroup_build = happy_path

#     cgroup_build = dummynet.CGroup.build_cgroup(cgroup_build, force=True)
#     cgroup_build.hard_clean()
#     assert True


# def test_cgroup_delete(sad_path):
#     cgroup_delete = sad_path
#     cgroup_delete.make_cgroup(exist_ok=True)

#     try:
#         cgroup_delete.delete_cgroup(not_exist_ok=False)
#     except Exception as e:
#         assert f"exists" in str(e)


# def test_cgroup_make(sad_path):
#     cgroup_make = sad_path

#     try:
#         cgroup_make.make_cgroup(exist_ok=True)
#         cgroup_make.make_cgroup(exist_ok=False)
#     except Exception as e:
#         assert f"exists" in str(e)


# def test_cgroup__add_cgroup_controller(sad_path):
#     cgroup_add_controller = sad_path

#     try:
#         cgroup_add_controller._add_cgroup_controller("cpu.wrongname")
#     except AssertionError as e:
#         assert "Controller " in str(e)


# def test_cgroup_input_validation(sad_path):
#     cgroup_input_validation = sad_path

#     try:
#         cgroup_input_validation.name = 12345
#         cgroup_input_validation.input_validation()
#     except AssertionError as e:
#         assert "Name must be a string" in str(e)


# def test_cgroup_set_limit(sad_path):
#     cgroup_set_limit = sad_path

#     try:
#         cgroup_set_limit.set_limit(cgroup_set_limit.controllers)
#     except AssertionError as e:
#         assert "must be in range" in str(
#             e
#         ) or "Controller not found in cgroup directory" in str(e)


# def test_cgroup_add_pid(sad_path):
#     cgroup_add_pid = sad_path

#     try:
#         cgroup_add_pid.add_pid(cgroup_add_pid.pid)
#     except AssertionError as e:
#         assert f"Process {cgroup_add_pid.pid} is not running." in str(e)


# def test_cgroup_hard_clean(sad_path):
#     cgroup_cleanup = sad_path
#     cgroup_cleanup.pid = os.getpid()
#     cgroup_cleanup.add_pid(cgroup_cleanup.pid)
#     try:
#         cgroup_cleanup.hard_clean()
#     except dummynet.errors.RunInfoError as e:
#         assert "No such file or directory" in str(e)
