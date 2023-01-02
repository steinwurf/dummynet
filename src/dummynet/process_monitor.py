import select
import textwrap
import os

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
            self.fds = {}
            self.log = log

        def add_fd(self, fd, callback):

            # Note that flags POLLHUP and POLLERR can be returned at any time
            # (even if were not asked for). So we don't need to explicitly
            # register for them.
            self.poller.register(fd, select.POLLIN)

            self.fds[fd] = callback

            self.log.debug(f"Poller: register process fd {fd}")

        def del_fd(self, fd):

            self.poller.unregister(fd)
            del self.fds[fd]

            self.log.debug(f"Poller: unregister process fd{fd}")

        def read_fd(self, fd):

            while True:
                try:
                    data = os.read(fd, 4096)
                except BlockingIOError:
                    break

                if not data:
                    break

                self.log.debug(f"Poller: read {len(data)} bytes from fd {fd}")

                # Call the callback
                self.fds[fd](data)

        def poll(self, timeout):

            fds = self.poller.poll(timeout)

            # First if we have any events, we need to read from the
            # file descriptors
            for fd, event in fds:
                if event & select.POLLIN:
                    self.read_fd(fd)

            for fd, event in fds:
                if event & select.POLLHUP:
                    self.del_fd(fd=fd)

                elif event & select.POLLERR:
                    self.del_fd(fd=fd)

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
                f"""\
                Process:
                    popen.pid: {self.popen.pid}
                    popen.stdout: {self.popen.stdout.fileno()}
                    popen.stderr: {self.popen.stderr.fileno()}
                    result: {self.result}
                """
            )

    class Stopped:
        def __init__(self) -> None:
            self.processes = []

        def add_process(self, process):
            self.processes.append(process)

        def stop(self):
            raise RuntimeError("Idle.stop() called")

        def validate(self):
            if not self.processes:
                # No processes in running or died
                raise errors.NoProcessesError()

            # Check that we have non daemon processes
            for process in self.processes:
                if not process.result.is_daemon:
                    return

            raise errors.AllDaemonsError()

    class Waiting:
        def __init__(self) -> None:
            self.processes = []

        def add_process(self, process):
            self.processes.append(process)

        def stop(self):
            raise RuntimeError("Waiting.stop() called")

        def validate(self):
            if not self.processes:
                # No processes in running or died
                raise errors.NoProcessesError()

            # Check that we have non daemon processes
            for process in self.processes:
                if not process.result.is_daemon:
                    return

            raise errors.AllDaemonsError()

    class Running:
        def __init__(self, processes, log) -> None:
            # A dictionary of running processes
            self.running = []

            # List of died processes
            self.died = []

            # The poller is used to wait for processes to terminate
            self.poller = ProcessMonitor.Poller(log=log)

        def add_process(self, process):
            # Make sure the process is running
            popen.poll()

            # The returncode should be None if the process is running
            if not popen.returncode is None:
                raise RuntimeError(
                    "Process not running: "
                    "returncode={} stderr={}".format(
                        popen.returncode, popen.stderr.read()
                    )
                )
            # Get the file descriptor
            process = ProcessMonitor.Process(popen, result, log=self.log)

            self.poller.add_fd(
                process.popen.stdout.fileno(), lambda data: result.stdout.append(data)
            )
            self.poller.add_fd(
                process.popen.stderr.fileno(), lambda data: result.stderr.append(data)
            )

            self.running.append(process)

        def poll(self, timeout):

            # Poll for events
            self.poller.poll(timeout)

            # Check if any process has died
            for process in self.running:
                process.popen.poll()
                if process.popen.returncode:
                    self.died.append(process)

            # Remove the died processes from the running list
            self.running = [p for p in self.running if p not in self.died]

        def _died(self):
            # Check if we had a normal exit
            if process.popen.returncode:

                # The process had a non-zero return code
                raise RuntimeError("Unexpected exit {}".format(process))

            if process.result.is_daemon:

                # The process was a daemon - these should not exit
                # until after the test is over
                raise errors.DaemonExitError(process)

        def stop(self):
            for process in self.running:

                self.poller.unregister(process)

                process.popen.poll()
                if process.popen.returncode:
                    raise RuntimeError("Process exited with error {}".format(process))

                process.popen.kill()

            self.running = {}
            self.died = []

        def keep_running(self):
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

    def __init__(self, log):
        """Create a new test monitor"""

        # The state of the monitor
        self.state = ProcessMonitor.Stopped()

        # The log object
        self.log = log

    def stop(self):
        """Stop all processes"""

        if isinstance(self.state, ProcessMonitor.Stopped):
            raise RuntimeError("Monitor in stopped state")

        if isinstance(self.state, ProcessMonitor.Waiting):
            raise RuntimeError("Monitor in waiting state")

        elif isinstance(self.state, ProcessMonitor.Running):
            self.state.stop()
            self.state = ProcessMonitor.Stopped()

    def add_process(self, popen, result):
        """Add a process to the monitor.

        :param popen: The subprocess.Popen object
        :param result: The dummynet.RunResult object
        """

        if isinstance(self.state, ProcessMonitor.Stopped):
            self.state = ProcessMonitor.Waiting()

        self.state.add_process(popen, result)

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

        if isinstance(self.state, ProcessMonitor.Stopped):
            # It ok to be in the stopped state here. Likely it is the user
            # who has called stop() in the while run() loop.
            return

        if isinstance(self.state, ProcessMonitor.Waiting):
            # We are waiting to run
            self.state.validate()

            self.state = ProcessMonitor.Running(
                processes=self.state.processes, log=self.log
            )

        # We are in the running state
        self.state.poll(timeout=timeout)

        if self.state.keep_running():
            return True

        self.stop()
