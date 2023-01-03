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

            self.log.debug(f"Poller: unregister process fd {fd}")

        def read_fd(self, fd):

            data = os.read(fd, 4096)

            if not data:
                return

            self.log.debug(f"Poller: read {len(data)} bytes from fd {fd}")

            # Call the callback
            self.fds[fd](data.decode("utf-8"))

        def poll(self, timeout):

            fds = self.poller.poll(timeout)

            self.log.debug(f"Poller: got {len(fds)} events")

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

        def __init__(self, popen, info):
            """Construct a new process object.

            :param popen: The subprocess.Popen object
            :param info: The dummynet.RunInfo object
            """

            self.popen = popen
            self.info = info

    class Stopped:
        """The stopped state. This is the initial and final state of the monitor."""

        def __init__(self):
            pass

    class Initializing:
        """The initializing state here we collect the processes to monitor."""

        def __init__(self):
            self.running = []

        def add_process(self, process):
            self.running.append(process)

        def validate(self):

            try:
                self._validate()
            except Exception:

                # Kill all processes
                for process in self.running:
                    process.popen.kill()
                raise

        def _validate(self):
            if not self.running:
                # No processes in running or died
                raise errors.NoProcessesError()

            # Check that we have non daemon processes
            for process in self.running:
                if not process.info.is_daemon:
                    return

            raise errors.AllDaemonsError()

    class Running:
        """The running state. Here we monitor the processes."""

        def __init__(self, log):
            # A dictionary of running processes
            self.running = []

            # List of died processes
            self.died = []

            # The poller is used to wait for processes to terminate
            self.poller = ProcessMonitor.Poller(log=log)

            self.log = log

        def add_process(self, process):

            # Make sure the process is running
            process.popen.poll()

            # The returncode should be None if the process is running
            if not process.popen.returncode is None:
                raise errors.ProcessExitError(process)

            self.running.append(process)

            def stdout_callback(data):
                process.info.stdout += data

                if process.info.stdout_callback:
                    process.info.stdout_callback(data)

            def stderr_callback(data):
                process.info.stderr += data

                if process.info.stderr_callback:
                    process.info.stderr_callback(data)

            # Get the file descriptor
            self.poller.add_fd(
                process.popen.stdout.fileno(),
                stdout_callback,
            )

            self.poller.add_fd(
                process.popen.stderr.fileno(),
                stderr_callback,
            )

        def poll(self, timeout):

            # Poll for events
            self.poller.poll(timeout)

            # Check if any process has died
            for process in self.running:

                process.popen.poll()

                if process.popen.returncode is not None:
                    self._died(process=process)

        def _died(self, process):

            self.died.append(process)
            self.running.remove(process)

            # Set the return code
            process.info.returncode = process.popen.returncode

            # Check if we had a normal exit
            if process.popen.returncode:

                # The process had a non-zero return code
                raise errors.RunInfoError(info=process.info)

            if process.info.is_daemon:

                # The process was a daemon - these should not exit
                # until after the test is over
                raise errors.DaemonExitError(process)

        def stop(self):
            """Stop all running processes."""

            self.log.debug("Stopping all processes")

            for process in self.running:

                self.poller.del_fd(process.popen.stdout.fileno())
                self.poller.del_fd(process.popen.stderr.fileno())

                process.popen.kill()

        def run(self, timeout):

            try:
                # Poll for events
                self.poll(timeout=timeout)
                return self.keep_running()

            except Exception:

                # Stop all processes
                self.stop()
                raise

        def keep_running(self):
            """Check if the test is over.

            The ProcessMonitor should continue running for as long as there
            are non daemon processes active.
            """

            for process in self.running:

                if not process.info.is_daemon:
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

        if isinstance(self.state, ProcessMonitor.Initializing):
            raise RuntimeError("Monitor in initializing state")

        if isinstance(self.state, ProcessMonitor.Running):
            self.state.stop()
            self.state = ProcessMonitor.Stopped()
        else:
            assert False, "Unknown state"

    def add_process(self, popen, info):
        """Add a process to the monitor.

        :param popen: The subprocess.Popen object
        :param info: The dummynet.RunInfo object
        """

        if isinstance(self.state, ProcessMonitor.Stopped):
            self.state = ProcessMonitor.Initializing()

        process = ProcessMonitor.Process(popen=popen, info=info)

        self.state.add_process(process=process)

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

        try:
            return self._run(timeout=timeout)

        except Exception as e:

            self.state = ProcessMonitor.Stopped()
            raise e

    def _run(self, timeout):

        if isinstance(self.state, ProcessMonitor.Stopped):
            # It ok to be in the stopped state here. Likely it is the user
            # who has called stop() in the while run() loop.
            return False

        if isinstance(self.state, ProcessMonitor.Initializing):

            # We are waiting to run
            self.state.validate()

            # Switch to the running state
            running = ProcessMonitor.Running(log=self.log)

            for process in self.state.running:
                running.add_process(process)

            self.state = running

        # We are in the running state
        return self.state.run(timeout=timeout)
