import select
import textwrap

from . import errors
from . import process


class ProcessMonitor:
    """
    The basic idea behind the monitor is to coordinate a process execution.

    Typically scenario:

    1. Run measurement software between two hosts
    2. Start a server side waiting for clients to connect
    3. Start a client and stop test once client exits

    We should also ensure that the server applications started in 2 keeps
    running throughout the test and that it is closed when the client
    application exits.
    """

    def __init__(self):
        """Create a new test monitor"""

        # A dictionary of running processes
        self.running = {}

        # List of died processes
        self.died = []

        # The poller is used to wait for processes to terminate
        self.poller = select.poll()

    def __enter__(self):
        pass

    def stop(self):
        for fd in self.running:
            popen = self.running[fd].popen
            popen.poll()
            if popen.returncode:
                raise RuntimeError(
                    "Process exited with error {}".format(self.running[fd])
                )
            popen.kill()
            popen.wait()

            self.poller.unregister(fd)

        self.running = {}
        self.died = []

    def __exit__(self, type, value, traceback):
        self.stop()

    def add_process(self, process):
        """Add a process to the monitor.

        :param process: The process to add to the monitor (a
            dummy.process.Process object)
        """

        # Make sure the process is running
        process.popen.poll()

        # The returncode should be None if the process is running
        if not process.popen.returncode is None:
            raise RuntimeError(
                "Process not running: "
                "returncode={} stderr={}".format(
                    process.popen.returncode, process.popen.stderr.read()
                )
            )
        # Get the file descriptor
        fd = process.popen.stdout.fileno()

        # Make sure we get signals when the process terminates
        self.poller.register(fd, select.POLLHUP | select.POLLERR)

        self.running[fd] = process

    def run(self, timeout=500):
        """Run the process monitor.

        :param timeout: A timeout in milliseconds. If this timeout
            expires we return.

        :return: True on timeout and processes are still running. If
            no processes are running anymore return False.

            The following simple loop can be used to keep the monitor
            running while waiting for processes to exit:

                while test_monitor.run():
                    pass
        """

        self._check_state()

        while self._keep_running():
            fds = self.poller.poll(timeout)

            if not fds:
                # We got a timeout
                return True

            for fd, event in fds:
                # Some events happened
                self._died(fd=fd, event=event)

        return False

    def _check_state(self):
        """Check that the state is valid."""

        if not self.running and not self.died:
            # No processes in running or died
            raise errors.NoProcessesError()

        # Check that we have non daemon processes
        for process in self.running.values():
            if not process.is_daemon:
                return

        for process in self.died:
            if not process.is_daemon:
                return

        raise errors.AllDaemonsError()

    def _died(self, fd, event):
        """A process has died.

        When a process dies we remove it from the running
        dict.

        :param fd: File descriptor for the process.
        :param event: The event that occurred.
        """

        # Checkt the event is one o
        assert event in [select.POLLHUP, select.POLLERR]

        self.poller.unregister(fd)

        died = self.running[fd]

        del self.running[fd]

        # Update the return code
        died.popen.wait()

        self.died.append(died)

        # Check if we had a normal exit
        if died.popen.returncode:

            # The process had a non-zero return code
            raise RuntimeError("Unexpected exit {}".format(died))

        if died.is_daemon:

            # The process was a daemon - these should not exit
            # until after the test is over
            raise errors.DaemonExitError(died)

    def _keep_running(self):
        """Check if the test is over.

        The TestMonitor should continue running for as long as there
        are non daemon processes active.
        """

        for process in self.running.values():
            if not process.is_daemon:
                # A process which is not a daemon is still running
                return True

        # Only daemon processes running
        return False
