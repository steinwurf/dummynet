import subprocess
import os
import time
import getpass

from . import run_info
from . import errors


class HostShell(object):
    """A shell object for running commands"""

    def __init__(self, log, sudo, process_monitor):
        """Create a new HostShell object

        :param log: The logger to use
        :param sudo: Whether to run commands with sudo
        :param process_monitor: The monitor is used
                                to track running processes and to stop them when the test is
                                finished.
        """
        self.log = log
        self.sudo = sudo
        self.process_monitor = process_monitor

    def run(self, cmd: str, cwd=None, env=None, timeout=None):
        """Run a synchronous command (blocking) with a timeout.

        :param cmd: The command to run
        :param cwd: The current working directory i.e. where the command will run
        :param env: The environment variables to set
        :param timeout: Maximum time (in seconds) to wait for the command to complete
        """

        if self.sudo:
            cmd = "sudo -k -S -E " + cmd

        if env is None:
            env = os.environ.copy()

        self.log.debug(cmd)

        return self.process_monitor.run_process(
            cmd=cmd, sudo=self.sudo, cwd=cwd, env=env, timeout=timeout
        )

    def run_async(self, cmd: str, daemon=False, cwd=None, env=None):
        """Run an asynchronous command (non-blocking).

        :param cmd: The command to run
        :param cwd: The current working directory i.e. where the command will
                    run
        """

        if self.sudo:
            cmd = "sudo -S -E " + cmd

        if env is None:
            env = os.environ.copy()

        self.log.debug(cmd)

        return self.process_monitor.run_process_async(
            cmd=cmd, sudo=self.sudo, daemon=daemon, cwd=cwd, env=env
        )
