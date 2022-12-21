class DummyNetError(Exception):
    """Base class for all dummynet exceptions"""

    def __init__(self, message):
        super().__init__(message)


class RunResultError(DummyNetError):
    """Exception for run result errors"""

    def __init__(self, result):
        super().__init__(str(result))
        self.result = result


class MatchError(DummyNetError):
    """Exception for output match errors"""

    def __init__(self, pattern, stream_name, output):
        """New MatchError object

        :param pattern: Pattern to search for in the list of output string
        :param stream_name: The name of the stream to match against
        :param output: The output to match against
        """

        message = f"Could not match '{pattern}' in {stream_name} output:\n" + output

        super().__init__(message)


class DaemonExitError(DummyNetError):
    """Exception for when the process monitor is started with only
    daemon processes.
    """

    def __init__(self, process):
        super().__init__(f"Unexpected daemon exit {process}")


class AllDaemonsError(DummyNetError):
    """Exception for when the process monitor is started with only
    daemon processes.
    """

    def __init__(self):
        super().__init__(f"All processes are daemons")


class NoProcessesError(DummyNetError):
    """Exception for when the process monitor is started without any
    processes.
    """

    def __init__(self):
        super().__init__(f"No processes were added")


class ProcessRunningError(DummyNetError):
    """Exception for when the process monitor is started without any
    processes.
    """

    def __init__(self, cmd, cwd):
        super().__init__(f"Process {cmd} in {cwd} not terminated while getting result")
