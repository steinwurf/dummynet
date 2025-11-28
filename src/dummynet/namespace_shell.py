from typing import Callable, Optional


class NamespaceShell:
    def __init__(self, name: str, shell):
        self.name = name
        self.shell = shell

    @property
    def log(self):
        return self.shell.log

    @property
    def process_monitor(self):
        return self.shell.process_monitor

    def run(self, cmd: str | list[str], cwd=None, env=None, timeout=None):
        """Run a command.
        :param cmd: The command to run
        :param cwd: The current working directory i.e. where the command will run
        :param env: The environment variables to set
        :param timeout: The timeout in seconds, if None then no timeout
        """
        cmd = self._add_netns_prefix(cmd)
        return self.shell.run(cmd=cmd, cwd=cwd, env=env, timeout=timeout)

    def poll_until(
        self,
        cmd: str | list[str],
        match_stdout: Optional[str] = None,
        match_stderr: Optional[str] = None,
        match_lambda: Optional[Callable] = None,
        timeout: int = 15,
        cwd=None,
        env=None,
    ):
        cmd = self._add_netns_prefix(cmd)
        return self.shell.poll_until(
            cmd=cmd,
            match_stdout=match_stdout,
            match_stderr=match_stderr,
            match_lambda=match_lambda,
            cwd=cwd,
            env=env,
            timeout=timeout,
        )

    def run_async(self, cmd: str | list[str], daemon=False, cwd=None):
        """Run a command in a shell asynchronously.
        :param cmd: The command to run
        :param cwd: The current working directory i.e. where the command will
            run
        """
        cmd = self._add_netns_prefix(cmd)
        return self.shell.run_async(cmd=cmd, daemon=daemon, cwd=cwd)

    def _add_netns_prefix(self, cmd: str | list[str]) -> str | list[str]:
        netns_exec_prefix = ["ip", "netns", "exec", f"{self.name}"]
        if isinstance(cmd, str):
            return " ".join(netns_exec_prefix) + " " + cmd
        if isinstance(cmd, list):
            return netns_exec_prefix + cmd
