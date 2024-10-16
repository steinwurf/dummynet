import select
import textwrap
import os
import subprocess
import signal
import getpass

from functools import lru_cache
from typing import Optional

from . import errors
from . import process
from . import run_info

# The cached sudo password
cached_sudo_password: Optional[str] = None


@lru_cache(maxsize=None)
def sudo_requires_password() -> bool:
    try:
        # Run 'sudo' to check if sudo requires a password
        # '--non-interactive' ensures sudo throws if it requires a password
        # '--reset-timestamp' ensures we ignore any possible cached credentials
        subprocess.run(
            ["sudo", "--non-interactive", "--reset-timestamp", "true"],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return False  # No password required
    except subprocess.CalledProcessError as e:
        if e.returncode == 1:
            return True  # Password required
        else:
            return False  # Some other error, assuming no password required


def update_sudo_password():
    """Cache the sudo password"""

    global cached_sudo_password

    if cached_sudo_password:
        # We already have a password cached
        return

    if not sudo_requires_password():
        # Sudo requires no password, skip prompting for one
        return

    cached_sudo_password = os.environ.get("DUMMYNET_SUDO_PASSWD", None)
    if cached_sudo_password:
        # Environment variable was set, use it instead of asking for a password
        return

    prompt = f"\n[sudo] password for {getpass.getuser()}: "

    cached_sudo_password = getpass.getpass(prompt=prompt) + "\n"


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
            self.log.debug(f"Poller: data: '{data}'")

            # Call the callback
            self.fds[fd](data.decode(encoding="utf-8", errors="replace"))

        def poll(self, timeout):
            fds = self.poller.poll(timeout)

            if len(fds) > 0:
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

        def wait_fd(self, fd):

            while fd in self.fds:
                self.poll(timeout=0.1)

    class Process:
        """A process object to track the state of a process"""

        def __init__(
            self, cmd: str, cwd, env, sudo, is_async, is_daemon, timeout, poller
        ):
            """Construct a new process object."""

            if sudo:
                update_sudo_password()

            self.popen = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=env,
                shell=True,
                # Get stdout and stderr as text
                text=True,
                # Make sure we can kill the process and the subprocesses
                # it may create:
                # https://alexandra-zaharia.github.io/posts/kill-subprocess-and-its-children-on-timeout-python/
                start_new_session=True,
            )

            # Pipe possible sudo password to the process
            if sudo and (cached_sudo_password != None):
                self.popen.stdin.write(cached_sudo_password)
                self.popen.stdin.flush()

            self.info = run_info.RunInfo(
                cmd=cmd,
                cwd=cwd,
                pid=self.popen.pid,
                stdout="",
                stderr="",
                returncode=None,
                is_async=is_async,
                is_daemon=is_daemon,
                timeout=timeout,
            )

            def stdout_callback(data):

                if self.info.stdout is None:
                    self.info.stdout = data
                else:
                    self.info.stdout += data

                if self.info.stdout_callback:
                    self.info.stdout_callback(data)

            def stderr_callback(data):

                if self.info.stderr is None:
                    self.info.stderr = data
                else:
                    self.info.stderr += data

                if self.info.stderr_callback:
                    self.info.stderr_callback(data)

            # Get the file descriptor
            poller.add_fd(
                self.popen.stdout.fileno(),
                stdout_callback,
            )

            poller.add_fd(
                self.popen.stderr.fileno(),
                stderr_callback,
            )

            if not is_async:

                try:
                    self.info.returncode = self.popen.wait(timeout=self.info.timeout)

                    poller.wait_fd(self.popen.stdout.fileno())
                    poller.wait_fd(self.popen.stderr.fileno())

                    if self.info.returncode != 0:
                        raise errors.RunInfoError(info=self.info)

                except subprocess.TimeoutExpired:

                    # The process did not exit
                    #
                    # This approach is taken from the subprocess documentation:
                    # https://docs.python.org/3/library/subprocess.html#subprocess.Popen.communicate

                    self.stop()

                    poller.wait_fd(self.popen.stdout.fileno())
                    poller.wait_fd(self.popen.stderr.fileno())

                    raise errors.TimeoutError(info=self.info)

        def is_running(self):
            """Poll the process and update the return code"""

            if self.info.returncode is not None:
                return True

            self.info.returncode = self.popen.poll()

            return self.info.returncode is None

        def stop(self):
            """Stop a process"""

            self.info.returncode = self.popen.poll()

            if self.info.returncode is not None:
                return

            # See start_new_sesstion in __init__ for why we use os.killpg
            os.killpg(os.getpgid(self.popen.pid), signal.SIGTERM)

            try:
                self.info.returncode = self.popen.wait(timeout=0.5)

            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(self.popen.pid), signal.SIGKILL)
                self.info.returncode = self.popen.wait()

    def __init__(self, log):
        """Create a new test monitor"""

        # The log object
        self.log = log

        # Daemons
        self.daemons = []

        # Programs (still running)
        self.processes = []

        # The poller is used to wait for processes to terminate
        self.poller = ProcessMonitor.Poller(log=log)

    def run_process(self, cmd: str, sudo, cwd=None, env=None, timeout=None):

        try:
            process = ProcessMonitor.Process(
                cmd=cmd,
                cwd=cwd,
                env=env,
                sudo=sudo,
                is_async=False,
                is_daemon=False,
                timeout=timeout,
                poller=self.poller,
            )

            return process.info
        except Exception as e:

            # Before we raise the exception we check if any other
            # errors have occoured

            try:
                self._validate_state()
            except Exception as nested:
                raise ExceptionGroup("Run failure", [e, nested])

            # Re-raise the exception to make sure the caller knows
            raise

    def run_process_async(self, cmd: str, sudo, daemon=False, cwd=None, env=None):
        try:
            process = ProcessMonitor.Process(
                cmd=cmd,
                cwd=cwd,
                env=env,
                sudo=sudo,
                is_async=True,
                is_daemon=daemon,
                timeout=None,
                poller=self.poller,
            )

            if daemon:
                self.daemons.append(process)
            else:
                self.processes.append(process)

            return process.info

        except:

            # Before we raise the exception we check if any other
            # errors have occoured
            self._validate_state()

            # Re-raise the exception to make sure the caller knows
            raise

    def keep_running(self, timeout=0.1):
        """Run the process monitor.

        :param timeout: A timeout in milliseconds. If this timeout
            expires we return.

        :return: True on timeout and processes are still running. If
            no processes are running anymore return False.

            The following simple loop can be used to keep the monitor
            running while waiting for processes to exit:

                while test_monitor.keep_running():
                    pass
        """

        # Check if we have any proccesses to wait for
        if not self.processes and self.daemons:
            raise errors.NoProcessesError()

        # Poll for output
        self.poller.poll(timeout)

        self._validate_state()

        # Check if there are any non-daemon processes running
        for process in self.processes:
            if process.info.returncode is None:
                return True

        return False

    def stop(self):
        """Stop all processes"""

        self._validate_state()

        for process in self.processes:
            process.stop()

        for daemon in self.daemons:
            daemon.stop()

        # Poll for output
        self.poller.poll(timeout=0.1)

        self.processes = []
        self.daemons = []

    def _validate_state(self):

        # Check if any processes have died with an error
        exceptions = []

        for process in self.processes:

            if process.is_running():
                continue

            if process.info.returncode != 0:
                exceptions.append(errors.RunInfoError(info=process.info))

        for daemon in self.daemons:
            if not daemon.is_running():
                exceptions.append(errors.DaemonExitError(info=daemon.info))

        if exceptions:
            raise ExceptionGroup("Invalid state", exceptions)
