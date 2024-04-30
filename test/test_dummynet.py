from dummynet import DummyNet
from dummynet import HostShell
from dummynet import ProcessMonitor

import dummynet

import logging
import time
import pytest
import os


def test_run():
    log = logging.getLogger("dummynet")

    sudo = os.getuid() != 0

    # The host shell used if we don't have a recording
    shell = HostShell(log=log, sudo=sudo, process_monitor=None)

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
    sudo = os.getuid() != 0

    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)

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

        while process_monitor.run():
            pass

        proc0.match(stdout="10 packets transmitted*", stderr=None)
        proc1.match(stdout="10 packets transmitted*", stderr=None)

    finally:
        # Clean up.
        net.cleanup()


def test_with_timeout():
    sudo = os.getuid() != 0

    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)
    log.addHandler(logging.StreamHandler())

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

        while process_monitor.run(timeout=500):
            if time.time() >= end_time:
                log.debug("Test timeout")
                process_monitor.stop()

    finally:
        # Clean up.
        net.cleanup()


def test_daemon_exit():
    sudo = os.getuid() != 0

    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)
    log.addHandler(logging.StreamHandler())

    # Create a process monitor
    process_monitor = ProcessMonitor(log=log)

    # The host shell used if we don't have a recording
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)

    # Run two commands on the host where the daemon will exit
    # before the non-daemon command
    shell.run_async(cmd="ping -c 5 8.8.8.8", daemon=True)
    shell.run_async(cmd="ping -c 50 8.8.8.8")

    with pytest.raises(dummynet.DaemonExitError):
        while process_monitor.run():
            pass


def test_all_daemons():
    sudo = os.getuid() != 0

    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)
    log.addHandler(logging.StreamHandler())

    # Create a process monitor
    process_monitor = ProcessMonitor(log=log)

    # The host shell used if we don't have a recording
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)

    # Run two commands on the host where the daemon will exit
    # before the non-daemon command
    shell.run_async(cmd="ping -c 5 8.8.8.8", daemon=True)
    shell.run_async(cmd="ping -c 50 8.8.8.8", daemon=True)

    with pytest.raises(dummynet.AllDaemonsError):
        while process_monitor.run():
            pass


def test_no_processes():
    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)
    log.addHandler(logging.StreamHandler())

    # Create a process monitor
    process_monitor = ProcessMonitor(log=log)

    # Nothing to do
    while process_monitor.run():
        pass


def test_hostshell_timeout():
    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)
    log.addHandler(logging.StreamHandler())

    # Create a process monitor
    process_monitor = ProcessMonitor(log=log)

    # The host shell
    shell = HostShell(log=log, sudo=False, process_monitor=process_monitor)

    start = time.time()
    # Check that we get a timeout if we run a command that takes too long
    with pytest.raises(dummynet.TimeoutError):
        # Run a command on the host
        shell.run(cmd="sleep 10", timeout=1100)

    difference = time.time() - start

    # Check that the timeout was more than 1 second
    assert difference > 1

    # Check that the timeout was less than 2 seconds
    assert difference < 2

    # Check that we don't get a timeout if we run that runs within the timeout
    shell.run(cmd="sleep 1", timeout=1200)

    # Nothing to do
    while process_monitor.run():
        pass


def test_cgroups():
    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)
    log.addHandler(logging.StreamHandler())

    sudo = os.getuid() != 0

    process_monitor = ProcessMonitor(log=log)
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)
    net = DummyNet(shell=shell)

    @pytest.fixture
    def sad_path():
        sad_cgroup = net.add_cgroup(
            name="test_cgroup_sad",
            shell=shell,
            log=log,
            default_path="/sys/fs/cgroup",
            controllers={"cpu.wrongname": 0, "memory.high": -200000000},
            pid=12345,
        )
        return sad_cgroup
    
    @pytest.fixture
    def happy_path():
        happy_cgroup = net.add_cgroup(
            name="test_cgroup_happy",
            shell=shell,
            log=log,
            default_path="/sys/fs/cgroup",
            controllers={"cpu.max": 0.5, "memory.high": 200000000},
            pid=os.getpid(),
        )
        return happy_cgroup

    def test_cgroup_build(happy_path):
        cgroup_build = happy_path
        try:
            log.debug(f"Testing cgroup: {cgroup_build.name} --> Happy path.\n" + "="*70 + "\n")
            cgroup_build = dummynet.CGroup.build_cgroup(cgroup_build)
            cgroup_build.hard_clean()
        except dummynet.errors.RunInfoError as e:
            raise Exception(f"Error during building cgroup: {e}")
        else:
            log.debug(f"Cgroup built: {cgroup_build.name} --> test successful.\n" + "="*70 + "\n")

    def test_cgroup_delete(sad_path):
        pass
    try:
        log.debug(f"Testing cgroup: {test_cgroup.name} --> Sad path.\n" + "="*70 + "\n")
        test_cgroup.delete_cgroup()
    except dummynet.errors.RunInfoError as e:
        if "Permission denied" in e.info.stderr:
            raise Exception("Permission denied. Run as root.")
        if "Directory not empty" in e.info.stderr:
            raise Exception(f"Cgroup directory not empty. Remove all processes from {test_cgroup}.")
    else:
        log.debug(f"Cgroup deleted: {test_cgroup.name} --> test successful.\n" + "-"*70 + "\n")

    try:
        test_cgroup.make_cgroup()
    except dummynet.errors.RunInfoError as e:
        assert e.info.returncode != 0, "Cgroup not created." 
    else:
        log.debug(f"Cgroup made: {test_cgroup.name} --> test successful.\n" + "-"*70 + "\n")

    try:
        test_cgroup.input_validation()
    except (AssertionError, FileNotFoundError) as e:
        raise Exception(f"Error validating input: {e}")
    else:
        log.debug(f"Input validated. --> test successful.\n" + "-"*70 + "\n")

    try:
        test_cgroup.add_cgroup_controller()
    except (dummynet.errors.RunInfoError, AssertionError) as e:    
        log.debug(f"Error caught: {e}\n Continuing...\n")
    else:
        log.debug(f"Controllers added: {list(test_cgroup.controllers.keys())} --> test successful.\n" + "-"*70 + "\n")

    try:
        test_cgroup.controllers = {"cpu.max": 0, "memory.high": -200000000}
        test_cgroup.set_limit()
    except AssertionError as e:
        log.debug(f"Error caught while setting limit: {e}\n Continuing...\n" + "-"*70 + "\n")
    else:
        log.debug(f"Limits set: {list(test_cgroup.controllers.values())} --> test successful.\n" + "-"*70 + "\n")

    try:
        test_cgroup.pid = [12345]
        test_cgroup.add_to_cgroup(pid=test_cgroup.pid)
    except AssertionError as e:
        log.debug(f"Error caught for non-existant PID: {e}\n Continuing...\n" + "-"*70 + "\n")
    else:
        log.debug(f"PID {test_cgroup.pid} added to cgroup: {test_cgroup.name} --> test successful.\n" + "-"*70 + "\n")

    try:
        test_cgroup.cleanup()
    except dummynet.errors.RunInfoError as e:
        log.debug(f"Error cleaning up: {e.info.stderr}\n Continuing...\n" + "-"*70 + "\n")
    else:
        log.debug(f"Cgroup cleaned: {test_cgroup.name} --> test successful.\n" + "-"*70 + "\n")
