import os
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

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

    def run(
        self, cmd: str | list[str], cwd=None, env=None, timeout=None
    ) -> run_info.RunInfo:
        """Run a synchronous command (blocking) with a timeout.

        :param cmd: The command to run
        :param cwd: The current working directory i.e. where the command will run
        :param env: The environment variables to set
        :param timeout: Maximum time (in seconds) to wait for the command to complete
        """

        if self.sudo:
            cmd = self._add_sudo_prefix(cmd)

        if env is None:
            env = os.environ.copy()

        self.log.info(f"{cmd!r}")

        return self.process_monitor.run_process(
            cmd=cmd, sudo=self.sudo, cwd=cwd, env=env, timeout=timeout
        )

    def poll_until(
        self,
        cmd: str,
        match_stdout: Optional[str] = None,
        match_stderr: Optional[str] = None,
        match_lambda: Optional[Callable] = None,
        timeout: int = 15,
        cwd=None,
        env=None,
    ) -> None:
        future = datetime.now() + timedelta(seconds=timeout)
        while datetime.now() <= future:
            try:
                runinfo = self.run(cmd, cwd=cwd, env=env)
            except errors.RunInfoError as err:
                runinfo = err.info
            try:
                if match_stdout or match_stderr:
                    return runinfo.match(stdout=match_stdout, stderr=match_stderr)
                elif match_lambda:
                    stdout = match_lambda(runinfo.stdout)
                    if stdout:
                        return
                    stderr = match_lambda(runinfo.stderr)
                    if stderr:
                        return
                else:
                    raise ValueError("No match statements were used for polling!")
            except errors.MatchError:
                pass
            time.sleep(0.2)

        raise errors.TimeoutError("Match not found within timeout")

    def run_async(self, cmd: str | list[str], daemon=False, cwd=None, env=None):
        """Run an asynchronous command (non-blocking).

        :param cmd: The command to run
        :param cwd: The current working directory i.e. where the command will
                    run
        """

        if self.sudo:
            cmd = self._add_sudo_prefix(cmd)

        if env is None:
            env = os.environ.copy()

        self.log.info(f"running {cmd!r}")

        return self.process_monitor.run_process_async(
            cmd=cmd, sudo=self.sudo, daemon=daemon, cwd=cwd, env=env
        )

    def _add_sudo_prefix(self, cmd: str | list[str]) -> str | list[str]:
        sudo_prefix = ["sudo", "--reset-timestamp", "--stdin", "--preserve-env"]
        if isinstance(cmd, str):
            return " ".join(sudo_prefix) + " " + cmd
        if isinstance(cmd, list):
            return sudo_prefix + cmd
