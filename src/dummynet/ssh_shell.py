class SSHShell:
    def __init__(self, shell, user, hostname, port=None):
        self.shell = shell
        self.user = user
        self.hostname = hostname
        self.port = port if port else 22
        self.cmd_prefix = f"ssh {self.user}@{self.hostname} -p {self.port}"

    def run(self, cmd, cwd=None):
        """Run a command.
        :param cmd: The command to run
        :param cwd: The current working directory i.e. where the command will run
        """

        return self.shell.run(cmd=f"{self.cmd_prefix} {cmd}", cwd=cwd)

    def run_async(self, cmd, daemon=False, cwd=None):
        """Run a command in a shell asynchronously.
        :param cmd: The command to run
        :param cwd: The current working directory i.e. where the command will run
        """

        return self.shell.run_async(cmd=f"{self.cmd_prefix} {cmd}", daemon=daemon, cwd=cwd)

