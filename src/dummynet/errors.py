class RunResultError(Exception):
    """Exception for TestDirctory::run"""

    def __init__(self, result):
        super(RunResultError, self).__init__(str(result))
        self.result = result


class MatchError(Exception):
    """Exception for output match errors"""

    def __init__(self, pattern, stream_name, output):
        """New MatchError object

        :param pattern: Pattern to search for in the list of output string
        :param stream_name: The name of the stream to match against
        :param output: The output to match against
        """

        message = f"Could not match '{pattern}' in {stream_name} output:\n" + output

        super(MatchError, self).__init__(message)
