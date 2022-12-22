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

    sudo = True if os.geteuid() == 0 else False

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

        assert namespaces == ["demo2", "demo1", "demo0"]

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

    log = logging.getLogger("dummynet")

    sudo = True if os.geteuid() == 0 else False

    process_monitor = ProcessMonitor()

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

        # process_monitor.add_process(proc0)
        # process_monitor.add_process(proc1)

        while process_monitor.run():
            pass

        proc0.result.match(stdout="10 packets transmitted*", stderr=None)
        proc1.result.match(stdout="10 packets transmitted*", stderr=None)

    finally:

        # Clean up.
        net.cleanup()


def test_with_timeout():

    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)
    log.addHandler(logging.StreamHandler())

    # Create a process monitor
    process_monitor = ProcessMonitor()

    # The host shell used if we don't have a recording
    shell = HostShell(log=log, sudo=True, process_monitor=process_monitor)

    # DummyNet wrapper that will prevent clean up from happening in playback
    # mode if an exception occurs
    net = DummyNet(shell=shell)

    try:

        # Run a command on the host
        out = net.run(cmd="ping -c 5 8.8.8.8")
        out.match(stdout="5 packets transmitted*", stderr=None)

        out = net.run_async(cmd="ping -c 5000 8.8.8.8")

        end_time = time.time() + 2

        while process_monitor.run():
            if time.time() >= end_time:
                log.debug("Test timeout")
                break

    finally:

        # Clean up.
        net.cleanup()

        # Close any running async commands
        process_monitor.stop()


def test_daemon_exit():

    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)
    log.addHandler(logging.StreamHandler())

    sudo = True if os.geteuid() == 0 else False

    # Create a process monitor
    process_monitor = ProcessMonitor()

    # The host shell used if we don't have a recording
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)

    try:

        # Run two commands on the host where the daemon will exit
        # before the non-daemon command
        shell.run_async(cmd="ping -c 5 8.8.8.8", daemon=True)
        shell.run_async(cmd="ping -c 50 8.8.8.8")

        with pytest.raises(dummynet.DaemonExitError):
            while process_monitor.run():
                pass

    finally:

        # Close any running async commands
        process_monitor.stop()


def test_all_daemons():

    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)
    log.addHandler(logging.StreamHandler())

    sudo = True if os.geteuid() == 0 else False

    # Create a process monitor
    process_monitor = ProcessMonitor()

    # The host shell used if we don't have a recording
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)

    try:

        # Run two commands on the host where the daemon will exit
        # before the non-daemon command
        shell.run_async(cmd="ping -c 5 8.8.8.8", daemon=True)
        shell.run_async(cmd="ping -c 50 8.8.8.8", daemon=True)

        with pytest.raises(dummynet.AllDaemonsError):
            while process_monitor.run():
                pass

    finally:

        # Close any running async commands
        process_monitor.stop()


def test_no_processes():

    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)
    log.addHandler(logging.StreamHandler())

    # Create a process monitor
    process_monitor = ProcessMonitor()

    try:

        with pytest.raises(dummynet.NoProcessesError):
            while process_monitor.run():
                pass

    finally:

        # Close any running async commands
        process_monitor.stop()


def test_pendingresult():

    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)
    log.addHandler(logging.StreamHandler())

    # Create a process monitor
    process_monitor = ProcessMonitor()

    sudo = True if os.geteuid() == 0 else False

    # The host shell used if we don't have a recording
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)

    # DummyNet wrapper that will prevent clean up from happening in playback
    # mode if an exception occurs
    net = DummyNet(shell=shell)

    try:

        # Run a command on the host
        out = net.run_async(cmd="ping -c 5 8.8.8.8")

        while process_monitor.run():
            pass

        out.result.match(stdout="5 packets transmitted*", stderr=None)

    finally:

        # Clean up.
        net.cleanup()

        # Close any running async commands
        process_monitor.stop()


def test_process_still_running():

    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)
    log.addHandler(logging.StreamHandler())

    # Create a process monitor
    process_monitor = ProcessMonitor()

    sudo = True if os.geteuid() == 0 else False

    # The host shell used if we don't have a recording
    shell = HostShell(log=log, sudo=sudo, process_monitor=process_monitor)

    # DummyNet wrapper that will prevent clean up from happening in playback
    # mode if an exception occurs
    net = DummyNet(shell=shell)

    try:

        # Run a command on the host
        out = net.run_async(cmd="ping -c 50 8.8.8.8")

        with pytest.raises(dummynet.ProcessRunningError):
            while process_monitor.run():
                out.result.match(stdout="5 packets transmitted*", stderr=None)

    finally:

        # Close any running async commands
        process_monitor.stop()

        # Clean up.
        net.cleanup()
