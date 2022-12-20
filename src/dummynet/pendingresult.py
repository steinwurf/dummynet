from . import runresult


class PendingResult:
    """The PendingResult object is returned when launching async operations.

    The PendingResult can be used to read output for the running processes.
    """

    def __init__(self, process, cmd, cwd):
        self.process = process
        self.cmd = cmd
        self.cwd = cwd
        self.result = None

    def match(self, stdout=None, stderr=None):
        if self.result:
            self.result.match(stdout=stdout, stderr=stderr)
        self.process.poll()
        if self.process.returncode is None:
            raise RuntimeError(
                "Process {} in {} not terminated "
                "while getting result".format(self.command, self.cwd)
            )
        self.result = runresult.RunResult(
            command=self.command,
            cwd=self.cwd,
            stdout=self.process.stdout.read(),
            stderr=self.process.stderr.read(),
            returncode=self.process.returncode,
        )
        self.result.match(stdout=stdout, stderr=stderr)
