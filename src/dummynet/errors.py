class DummyNetError(Exception):
    """Base class for all dummynet exceptions"""

    def __init__(self, message):
        super().__init__(message)


class RunInfoError(DummyNetError):
    """Exception for run result errors"""

    def __init__(self, info):
        super().__init__(message="runinfo error")

        # We wait with stringifying the info until needed since polling stdout
        # and stderr still happen after the exception is created. We maybe
        # should do this differently but for now this works. Alternatively we
        # could capture the output at the time of exception creation e.g. in
        # the process monitor.
        self.info = info

    def __str__(self):
        return str(self.info)

    def __repr__(self):
        return f"RunInfoError({repr(self.info)})"


class TimeoutError(DummyNetError):
    """Exception for timeout errors"""

    def __init__(self, info):
        super().__init__(message="timeout error")

        # See RunInfoError for explanation
        self.info = info

    def __str__(self):
        return str(self.info)

    def __repr__(self):
        return f"TimeoutError({repr(self.info)})"


class MatchError(DummyNetError):
    """Exception for output match errors"""

    def __init__(self, pattern, stream_name, output):
        """New MatchError object

        :param pattern: Pattern to search for in the list of output string
        :param stream_name: The name of the stream to match against
        :param output: The output to match against
        """

        message = f"Could not match '{pattern}' in {stream_name} output:\n{output}"

        super().__init__(message)


class DaemonExitError(DummyNetError):
    """Exception for when the process monitor is started with only
    daemon processes.
    """

    def __init__(self, info):
        super().__init__(f"Unexpected daemon exit: {str(info)} ")


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


class ProcessExitError(DummyNetError):
    """Exception for when the process monitor is started with an already terminated process
    process
    """

    def __init__(self, process):
        super().__init__(f"Process exited before process monitor: {process.info} ")
