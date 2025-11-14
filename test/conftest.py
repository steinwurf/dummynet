from dummynet.dummy_net import DummyNet
from dummynet.host_shell import HostShell
from dummynet.process_monitor import ProcessMonitor, sudo_requires_password
import dummynet
from getpass import getpass
from typing import Generator
import pytest
import logging
import os


def pytest_configure(config):
    # Set root password once on xdist master.
    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    if worker_id is None and sudo_requires_password():
        os.environ["DUMMYNET_SUDO_PASSWD"] = getpass("[sudo] password for root: ")


@pytest.fixture
def log() -> logging.Logger:
    """Create and configure a logger for tests"""
    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)
    return log


@pytest.fixture
def sudo() -> bool:
    """Check if we need to run as sudo"""
    return os.getuid() != 0


@pytest.fixture
def process_monitor(log) -> ProcessMonitor:
    """Create a process monitor"""
    return dummynet.ProcessMonitor(log=log)


@pytest.fixture
def shell(log, sudo, process_monitor) -> HostShell:
    """Create a host shell"""
    return dummynet.HostShell(log=log, sudo=sudo, process_monitor=process_monitor)


@pytest.fixture
def net(shell) -> Generator[DummyNet, None, None]:
    """Create a DummyNet instance"""
    net = dummynet.DummyNet(shell=shell)
    # Ensure we are not reusing a namespace
    netns, cgroups, links = net.netns_list(), net.cgroup_list(), net.link_list()
    assert links == [], f"setup: expected no links, found: {links!r}."
    assert cgroups == [], f"setup: expected no cgroups, found: {cgroups!r}."
    assert netns == [], f"setup: expected no namespaces, found: {netns!r}."

    try:
        yield net
    finally:
        # Ensure cleanup happened
        netns, cgroups, links = net.netns_list(), net.cgroup_list(), net.link_list()
        assert links == [], f"teardown: expected no links, found: {links!r}."
        assert cgroups == [], f"teardown: expected no cgroups, found: {cgroups!r}."
        assert netns == [], f"teardown: expected no namespaces, found: {netns!r}."
