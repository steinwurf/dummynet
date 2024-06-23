import fnmatch

from . import errors


class RunInfo:
    """Stores the results from running a command

    :ivar cmd: see :meth:`RunInfo.__init__`
    :ivar cwd: see :meth:`RunInfo.__init__`
    :ivar pid: see :meth:`RunInfo.__init__`
    :ivar stdout: see :meth:`RunInfo.__init__`
    :ivar stderr: see :meth:`RunInfo.__init__`
    :ivar returncode: see :meth:`RunInfo.__init__`
    :ivar is_async: see :meth:`RunInfo.__init__`
    :ivar is_daemon: see :meth:`RunInfo.__init__`
    :ivar timeout: see :meth:`RunInfo.__init__`
    :ivar stdout_callback: The callback to be called when the standard output
                            stream is received  (default: None). The callback
                            should accept a single argument which is the data
                            received.
    :ivar stderr_callback: The callback to be called when the standard error
                            stream is received  (default: None). The callback
                            should accept a single argument which is the data
                            received.
    """

    def __init__(
        self, cmd, cwd, pid, stdout, stderr, returncode, is_async, is_daemon, timeout
    ):
        """Create a new object

        :param cmd: The command that was executed
        :param cwd: Current working directory i.e. path where the command was executed
        :param pid: The process ID of the command
        :param stdout: The standard output stream generated by the command
        :param stderr: The standard error stream generated by the command
        :param returncode: The return code set after invoking the command
        :param is_async: Whether the command was run asynchronously
        :param is_daemon: Whether the command was run as a daemon
        :param timeout: The timeout in seconds, if None then no timeout
        """

        self.cmd = cmd
        self.cwd = cwd
        self.pid = pid
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.is_async = is_async
        self.is_daemon = is_daemon
        self.stdout_callback = None
        self.stderr_callback = None
        self.timeout = timeout

    def match(self, stdout=None, stderr=None):
        """Matches the lines in the output with the pattern. The match
        pattern can contain basic wildcards, see
        https://docs.python.org/2/library/fnmatch.html
        For convenience::

            +-----------------------------------------+
            |Pattern|Meaning                          |
            +-----------------------------------------+
            |*      |matches everything               |
            +-----------------------------------------+
            |?      |matches any single character     |
            +-----------------------------------------+
            |[seq]  |matches any character in seq     |
            +-----------------------------------------+
            |[!seq] |matches any character not in seq |
            +-----------------------------------------+

        Simple example::

            out.match(stdout='*success*')

        :param stdout: Pattern to search for in the list of stdout string
        :param stderr: Pattern to search for in the list of stderr string

        :raises MatchError: If the pattern is not found in the output
        """

        if stdout is not None:
            self._match(stdout, "stdout", self.stdout)

        if stderr is not None:
            self._match(stderr, "stderr", self.stderr)

    def _match(self, pattern, stream_name, output):
        """Matches the lines in the output with the pattern.

        :param pattern: Pattern to search for in the list of output string
        :param stream_name: The name of the stream to match against
        :param output: The output to match against
        """

        if output is None:
            raise errors.MatchError(
                pattern=pattern, stream_name=stream_name, output=output
            )

        match_lines = fnmatch.filter(output.splitlines(), pattern)

        if len(match_lines) == 0:
            raise errors.MatchError(
                pattern=pattern, stream_name=stream_name, output=output
            )

    def __str__(self):
        """Print the RunInfo object as a string"""
        run_string = (
            "RunInfo\n"
            "command: {command}\n"
            "cwd: {cwd}\n"
            "pid: {pid}\n"
            "returncode: {returncode}\n"
            "stdout: \n{stdout}"
            "stderr: \n{stderr}"
            "is_async: {is_async}\n"
            "is_daemon: {is_daemon}\n"
            "timeout: {timeout}\n"
        )

        return run_string.format(
            command=self.cmd,
            cwd=self.cwd,
            pid=self.pid,
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
            is_async=self.is_async,
            is_daemon=self.is_daemon,
            timeout=self.timeout,
        )
