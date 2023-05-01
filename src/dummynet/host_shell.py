import subprocess
import sys
import os

from . import run_info
from . import errors


class HostShell(object):
    """A shell object for running commands"""

    def __init__(self, log, sudo: bool, process_monitor):
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

    def run(self, cmd: str, cwd=None, env=None):
        """Run a synchronous command (blocking).

        :param cmd: The command to run
        :param cwd: The current working directory i.e. where the command will
                    run
        :param env: The environment variables to set
        """

        if self.sudo:
            cmd = "sudo " + cmd

        if env is None:
            env = os.environ.copy()

        self.log.debug(cmd)

        # Launch the command
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            shell=True,
            # Get stdout and stderr as text
            text=True,
        )

        # Here we wait for the process to exit
        # Warning: this can fail with large numbers of fds!
        stdout, stderr = process.communicate()
        returncode = process.wait()

        info = run_info.RunInfo(
            cmd=cmd,
            cwd=cwd,
            pid=process.pid,
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            is_async=False,
            is_daemon=False,
        )

        if info.returncode != 0:
            raise errors.RunInfoError(info=info)

        return info

    def run_async(self, cmd: str, daemon=False, cwd=None, env=None):
        """Run an asynchronous command (non-blocking).

        :param cmd: The command to run
        :param cwd: The current working directory i.e. where the command will
                    run
        """
        if self.sudo:
            cmd = "sudo " + cmd

        if env is None:
            env = os.environ.copy()

        self.log.debug(cmd)

        # Launch the command
        popen = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            shell=True,
            # Get stdout and stderr as text
            text=True,
        )

        info = run_info.RunInfo(
            cmd=cmd,
            cwd=cwd,
            pid=popen.pid,
            stdout="",
            stderr="",
            returncode=None,
            is_async=True,
            is_daemon=daemon,
        )

        self.process_monitor.add_process(popen=popen, info=info)

        return info
