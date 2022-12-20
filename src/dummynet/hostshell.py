import subprocess
import time

from . import runresult
from . import pendingresult
from . import errors


class HostShell(object):
    """A shell object for running commands"""

    def __init__(self, log, sudo: bool, test_monitor):
        """Create a new HostShell object
        :param log: The logger to use
        :param sudo: Whether to run commands with sudo
        :param testmonitor: The test monitor to use. The test monitor is used
            to track running processes and to stop them when the test is
            finished.
        """
        self.log = log
        self.sudo = sudo
        self.test_monitor = test_monitor

    def run(self, cmd: str, cwd=None):
        """Run a synchronous command (blocking).
        :param cmd: The command to run
        :param cwd: The current working directory i.e. where the command will
            run
        """

        if self.sudo:
            cmd = "sudo " + cmd

        self.log.debug(cmd)

        # Launch the command
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            shell=True,
            # Get stdout and stderr as text
            text=True,
        )

        # Warning: this can fail with large numbers of fds!
        stdout, stderr = process.communicate()
        returncode = process.wait()

        result = runresult.RunResult(
            command=cmd, cwd=cwd, stdout=stdout, stderr=stderr, returncode=returncode
        )

        if result.returncode != 0:
            raise errors.RunResultError(result=result)

        return result

    def run_async(self, cmd: str, daemon=False, cwd=None):
        """Run an asynchronous command (non-blocking).
        :param cmd: The command to run
        :param cwd: The current working directory i.e. where the command will
            run
        """
        if self.sudo:
            cmd = "sudo " + cmd

        self.log.debug(cmd)

        # Launch the command
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            shell=True,
            # Get stdout and stderr as text
            text=True,
        )

        self.test_monitor.add_process(process=process, cmd=cmd, cwd=cwd, daemon=daemon)

        # If we are launching a daemon we wait 0.5 sec for
        # it to launch
        if daemon:
            time.sleep(0.5)

        return pendingresult.PendingResult(process=process, cmd=cmd, cwd=cwd)
