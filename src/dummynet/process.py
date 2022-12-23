import textwrap

from . import run_result
from . import errors


class Process(object):
    """Process object to track the state of a process

    :ivar popen: The subprocess.Popen object
    :ivar result: The :ref:`dummynetrunresult` object
    """

    def __init__(self, popen, result):
        """ " Construct a new process object.

        :param popen: The subprocess.Popen object
        :param result: The :ref:`dummynetrunresult` object
        """
        self.popen = popen
        self.result = result
