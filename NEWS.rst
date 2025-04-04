News for dummynet
=================
This file lists the major changes between versions. For a more detailed list of
every change, see the Git log.

Latest
------
* Major: Changed the API of the `CGroup`.

4.0.1
-----
* Patch: Fix issue where the output of a process was being truncated at 4096
  bytes.

4.0.0
-----
* Major: Sudo now ignores the user's cached credentials to avoid losing the
  caching during a run.
* Minor: Sudo will now utilize passwordless sudo when available.
* Minor: Allow environment variable `DUMMYNET_SUDO_PASSWD` as an alternative to
  setting the sudo password from stdin.

3.0.0
-----
* Major: Requires Python 3.11 or later (due to use of ExceptionGroup).
* Major: Rename `ProcessMonitor.run`to `ProcessMonitor.keep_running`.

2.6.0
-----
* Minor: Added class ``CGroup`` to add support for managing cgroups and limiting
  resources used by dummynet.
* Patch: Fixed issue with file-handling commands in cgroups.

2.5.0
-----
* Minor: Added support for setting a timeout on `HostShell.run` and
  `NamespaceShell.run`.

2.4.1
-----
* Patch: Allow processes to output non-UTF-8 characters to stdout and stderr by
  replacing with '?'.

2.4.0
-----
* Minor: Added ``process_monitor`` property to ``NamespaceShell`` so that
  it's compatible with ``HostShell``.

2.3.0
-----
* Minor: Make sure we get stdout and stderr if a daemon process exits
  unexpectedly before monitor

2.2.0
-----
* Minor: Add pid to RunInfo
* Minor: Make sure we get stdout and stderr if a process exists before monitor

2.1.0
-----
* Minor: Sort namespace names returned by dummynet.netns.list.
* Patch: Fix issue when raising `RunInfoError` in `HostShell.run`.

2.0.0
-----
* Major: Yet another rewrite to better support output from multiple processes.
* Major: Rewrite of dummynet to add support for managing multiple processes.

1.0.2
-----
* Patch: Correct issue with dummynet vs dummynet-python
  naming.

1.0.1
-----
* Patch: Fix `DockerShell.run_async`.

1.0.0
-----
* Major: Initial release.
