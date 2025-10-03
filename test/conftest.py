from getpass import getpass
import os

from dummynet.process_monitor import sudo_requires_password


def pytest_configure(config):
    # Set root password once on xdist master.
    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    if worker_id is None and sudo_requires_password():
        os.environ["DUMMYNET_SUDO_PASSWD"] = getpass("[sudo] password for root: ")
