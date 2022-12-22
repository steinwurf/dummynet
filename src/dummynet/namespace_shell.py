class NamespaceShell:
    def __init__(self, name, shell):
        self.name = name
        self.shell = shell

    def run(self, cmd, cwd=None):
        """Run a command.
        :param cmd: The command to run
        :param cwd: The current working directory i.e. where the command will
            run
        """

        return self.shell.run(cmd=f"ip netns exec {self.name} {cmd}", cwd=cwd)

    def run_async(self, cmd, daemon=False, cwd=None):
        """Run a command in a shell asynchronously.
        :param cmd: The command to run
        :param cwd: The current working directory i.e. where the command will
            run
        """

        return self.shell.run_async(
            cmd=f"ip netns exec {self.name} {cmd}", daemon=daemon, cwd=cwd
        )
