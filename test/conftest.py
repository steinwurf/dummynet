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
def net(shell) -> Generator[DummyNet]:
    """Create a DummyNet instance"""
    net = dummynet.DummyNet(shell=shell)
    # Ensure we are not reusing a namespace
    netns, links = net.netns_list(), net.link_list()
    assert netns == [], f"pre-run: expected no namespaces, found: {netns}."
    assert links == [], f"pre-run: expected no links, found: {links}."

    try:
        yield net
    finally:
        # Ensure cleanup happened
        netns, links = net.netns_list(), net.link_list()
        assert netns == [], f"post-run: expected no namespaces, found: {netns}."
        assert links == [], f"post-run: expected no links, found: {links}."
