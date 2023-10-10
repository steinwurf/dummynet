class NamespaceShell:
    def __init__(self, name, shell):
        self.name = name
        self.shell = shell

    @property
    def process_monitor(self):
        return self.shell.process_monitor

    def run(self, cmd: str, cwd=None, env=None, timeout=None):
        """Run a command.
        :param cmd: The command to run
        :param cwd: The current working directory i.e. where the command will run
        :param env: The environment variables to set
        :param timeout: The timeout in seconds, if None then no timeout
        """

        return self.shell.run(
            cmd=f"ip netns exec {self.name} {cmd}", cwd=cwd, env=env, timeout=timeout
        )

    def run_async(self, cmd, daemon=False, cwd=None):
        """Run a command in a shell asynchronously.
        :param cmd: The command to run
        :param cwd: The current working directory i.e. where the command will
            run
        """

        return self.shell.run_async(
            cmd=f"ip netns exec {self.name} {cmd}", daemon=daemon, cwd=cwd
        )
