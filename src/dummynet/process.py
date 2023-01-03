import textwrap

from . import run_info
from . import errors


class Process(object):
    """Process object to track the state of a process

    :ivar popen: The subprocess.Popen object
    :ivar result: The :ref:`dummynetRunInfo` object
    """

    def __init__(self, popen, result):
        """ " Construct a new process object.

        :param popen: The subprocess.Popen object
        :param result: The :ref:`dummynetRunInfo` object
        """
        self.popen = popen
        self.result = result
