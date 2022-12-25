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

    class Poller:
        def __init__(self, log):
            self.poller = select.poll()
            self.log = log

        def register(self, process):

            self.poller.register(
                process.popen.stdout.fileno(),
                select.POLLHUP | select.POLLERR | select.POLLIN,
            )

            self.poller.register(
                process.popen.stderr.fileno(),
                select.POLLIN,
            )

            self.log.debug("Registered process {}".format(process))

        def unregister(self, process):

            self.poller.unregister(process.popen.stdout.fileno())
            self.poller.unregister(process.popen.stderr.fileno())

            self.log.debug("Unregistered process {}".format(process))

        def poll(self, timeout):
            return self.poller.poll(timeout)

    class Process:
        """A process object to track the state of a process"""

        def __init__(self, popen, result, log):
            """Construct a new process object.

            :param popen: The subprocess.Popen object
            :param result: The dummynet.RunResult object
            :param log: The log object
            """

            self.popen = popen
            self.result = result
            self.log = log

        def has_fd(self, fd):
            """Check if the process has a file descriptor.

            :param fd: The file descriptor to check
            """
            if self.popen.stdout.fileno() == fd:
                return True

            if self.popen.stderr.fileno() == fd:
                return True

            return False

        def read(self, fd):
            """Read from a file descriptor.

            :param fd: The file descriptor to read from
            """
            if self.popen.stdout.fileno() == fd:
                self.result.stdout += self.popen.stdout.read()
                return

            if self.popen.stderr.fileno() == fd:
                self.result.stderr += self.popen.stderr.read()
                return

            raise RuntimeError("Unknown fd {}".format(fd))

        def __str__(self):
            return textwrap.dedent(
                """\
                Process:
                    popen: {}
                    result: {}
                """.format(
                    self.popen, self.result
                )
            )

    def __init__(self, log):
        """Create a new test monitor"""

        # A dictionary of running processes
        self.running = []

        # List of died processes
        self.died = []

        # The poller is used to wait for processes to terminate
        self.poller = ProcessMonitor.Poller(log=log)

        # The log object
        self.log = log

    def __enter__(self):
        pass

    def stop(self):
        for process in self.running:

            self.poller.unregister(process)

            process.popen.poll()
            if process.popen.returncode:
                raise RuntimeError("Process exited with error {}".format(process))

            process.popen.kill()

        self.running = {}
        self.died = []

    def __exit__(self, type, value, traceback):
        self.stop()

    def add_process(self, popen, result):
        """Add a process to the monitor.

        :param popen: The subprocess.Popen object
        :param result: The dummynet.RunResult object
        """

        # Make sure the process is running
        popen.poll()

        # The returncode should be None if the process is running
        if not popen.returncode is None:
            raise RuntimeError(
                "Process not running: "
                "returncode={} stderr={}".format(popen.returncode, popen.stderr.read())
            )
        # Get the file descriptor
        process = ProcessMonitor.Process(popen, result, log=self.log)

        self.poller.register(process)

        self.running.append(process)

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

            print(f"on fds: {fds}")
            print(f"select.POLLIN: {select.POLLIN}")
            print(f"select.POLLHUP: {select.POLLHUP}")
            print(f"select.POLLERR: {select.POLLERR}")

            for fd, event in fds:
                # Some events happened
                if event == select.POLLIN:
                    # We got data
                    self._read(fd=fd)
                elif event in [select.POLLHUP, select.POLLERR]:
                    # The process died
                    self._died(fd=fd)
                else:
                    raise RuntimeError("Unknown event {}".format(event))

        self.stop()
        return False

    def _check_state(self):
        """Check that the state is valid."""

        if not self.running and not self.died:
            # No processes in running or died
            raise errors.NoProcessesError()

        # Check that we have non daemon processes
        for process in self.running:
            if not process.result.is_daemon:
                return

        for process in self.died:
            if not process.result.is_daemon:
                return

        raise errors.AllDaemonsError()

    def _find_process(self, fd):
        """Find a process by file descriptor.

        :param fd: The file descriptor to find
        """

        for process in self.running:
            if process.has_fd(fd):
                return process

        raise RuntimeError(f"Unknown process for fd {fd}")

    def _read(self, fd):
        """A process has written data.

        :param fd: File descriptor for the process.
        :param event: The event that occurred.
        """
        process = self._find_process(fd)

        # Read the data
        process.read(fd)

    def _died(self, fd):
        """A process has died.

        When a process dies we remove it from the running
        dict.

        :param fd: File descriptor for the process.
        """

        process = self._find_process(fd)

        # We found the process
        self.poller.unregister(process)

        self.running.remove(process)
        self.died.append(process)

        # Update the return code
        process.popen.wait()

        # Check if we had a normal exit
        if process.popen.returncode:

            # The process had a non-zero return code
            raise RuntimeError("Unexpected exit {}".format(process))

        if process.result.is_daemon:

            # The process was a daemon - these should not exit
            # until after the test is over
            raise errors.DaemonExitError(process)

    def _keep_running(self):
        """Check if the test is over.

        The ProcessMonitor should continue running for as long as there
        are non daemon processes active.
        """

        for process in self.running:
            if not process.result.is_daemon:
                # A process which is not a daemon is still running
                return True

        # Only daemon processes running
        return False
