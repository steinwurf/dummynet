import textwrap

from . import run_result
from . import errors


class Process(object):
    def __init__(self, popen, cmd, cwd, is_daemon, is_async):
        self.popen = popen
        self.cmd = cmd
        self.cwd = cwd
        self.is_daemon = is_daemon
        self.is_async = is_async
        self._result = None

    @property
    def result(self):

        if self._result:
            return self._result

        self.popen.poll()

        if self.popen.returncode is None:
            raise errors.ProcessRunningError(self.cmd, self.cwd)

        self._result = run_result.RunResult(
            cmd=self.cmd,
            cwd=self.cwd,
            stdout=self.popen.stdout.read(),
            stderr=self.popen.stderr.read(),
            returncode=self.popen.returncode,
            is_async=self.is_async,
            is_daemon=self.is_daemon,
        )

        return self._result

    def __str__(self):
        return str(self._result)
