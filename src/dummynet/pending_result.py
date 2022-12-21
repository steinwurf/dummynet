from . import run_result
from . import errors


class PendingResult:
    """The PendingResult object is returned when launching async operations.

    The PendingResult can be used to read output for the running processes.
    """

    def __init__(self, process, cmd, cwd):
        self.process = process
        self.cmd = cmd
        self.cwd = cwd
        self._result = None

    @property
    def result(self):

        if self._result:
            return self._result

        self.process.poll()

        if self.process.returncode is None:
            raise errors.ProcessRunningError(self.cmd, self.cwd)

        self._result = run_result.RunResult(
            cmd=self.cmd,
            cwd=self.cwd,
            stdout=self.process.stdout.read(),
            stderr=self.process.stderr.read(),
            returncode=self.process.returncode,
        )

        return self._result
