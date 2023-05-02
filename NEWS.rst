News for dummynet
=================
This file lists the major changes between versions. For a more detailed list of
every change, see the Git log.

Latest
------
* tbd

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
