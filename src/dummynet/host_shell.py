import subprocess
import os
import time

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

    def run(self, cmd: str, cwd=None, env=None, timeout=None):
        """Run a synchronous command (blocking) with a timeout.

        :param cmd: The command to run
        :param cwd: The current working directory i.e. where the command will run
        :param env: The environment variables to set
        :param timeout: Maximum time (in milliseconds) to wait for the command to complete
        """

        timeout_secs = timeout / 1000.0 if timeout is not None else None

        if self.sudo:
            cmd = "sudo " + cmd

        if env is None:
            env = os.environ.copy()

        self.log.debug(cmd)

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

        try:
            # Here we wait for the process to exit
            # Warning: this can fail with large numbers of fds!
            start = time.time()
            stdout, stderr = process.communicate(timeout=timeout_secs)
            end = time.time()
            remaining_secs = (
                None if timeout_secs is None else timeout_secs - (end - start)
            )
            if remaining_secs is not None and remaining_secs <= 0.0:
                remaining_secs = 0.1
            returncode = process.wait(timeout=remaining_secs)

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

        except subprocess.TimeoutExpired:
            raise errors.TimeoutError(
                f"The command '{cmd}' timed out after {timeout} seconds."
            )

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
