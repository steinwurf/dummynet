News for dummynet
=================
This file lists the major changes between versions. For a more detailed list of
every change, see the Git log.

Latest
------
* Minor: Added netns_use to allow an existing namespace to be used instead of
  creating a new one.
* Patch: Update dependency `psutil` from version `7.0.0` to version `7.2.1`.

10.1.0
------
* Minor: `RunInfo` now takes the optional arguments `cpu_system`, `cpu_user`,
  `mem_rss`, `mem_vms`. The same arguments are also properties of `RunInfo`,
  together with the helper `cpu_total` property.
* Minor: `RunInfo` repr and string representation changed to be more concise
  and easy to read.
* Minor: New feature with incremental CPU and Memory Usage statistics added
  to `RunInfo` after each sync from `process_monitor.keep_running` and
  `process.is_running` calls.
* Patch: Fixed extra newline printed before sudo request.

10.0.0
------
* Major: `update_sudo_password` will now throw `RuntimeError` early if given
  sudo password is incorrect.
* Patch: Fixed `update_sudo_password` to function with `pytest-xdist`.

9.2.1
-----
* Patch: Fixed bad sudo argument in `HostShell` causing failures when called.

9.2.0
-----
* Minor: Allow direct non-shell wrapped execution by using a list to the `cmd`
  arguments in `ProcessMonitor.run_process_async`, `ProcessMonitor.run_process`,
  `HostShell.run_async`, `HostShell.run`, `NamespaceShell.run_async` and
  `NamespaceShell.run`.
* Minor: Add optional `timeout` arguments to `ProcessMonitor.stop_process_async` and
  `ProcessMonitor.stop`.

9.1.0
-----
* Minor: Add `stop_process_async` function to `ProcessMonitor` to allow early return of
  processes running as async.

9.0.0
-----
* Major: Cleanup stage will now always validate DummyNets internal state for processes,
  meaning bad use will now correctly throw exceptions, when invalid state previously
  was silently ignored.
* Major: Cleanup will now cleanly handle invalid state and still clean up all managed
  networks, namespaces and cgroups.

8.0.1
-----
* Patch: Handle `DummyNet.route` rollback by warning if `DummyNet.down` is used
  against the same interface.

8.0.0
-----
* Major: iptables and tc lookup logic now requires a proper PATH variable to be set.
* Minor: Most commands now wait to return until the change is available to use.
* Minor: `DummyNet.link_delete` and `DummyNet.netns_delete` will now cleanly handle
  their cleanup process.
* Minor: `DummyNet.up` and `DummyNet.down` will now correctly restore previous
  administrative states on cleanup.

7.0.1
-----
* Patch: Correctly handle no-sudo case in `sudo_requires_password()` helper.

7.0.0
-----
* Major: `DummyNet.link_veth_add`, `DummyNet.bridge_add`, `DummyNet.link_vlan_add`
  now handle their own cleanup correctly in `net.cleanup()` when inside the system
  scope.
* Minor: Added commands `DummyNet.addr_del` and `DummyNet.link_vlan_add`.
* Minor: Make `Scoped` classes have `str()` functionality in addition to its
  `.scoped` attribute.
* Patch: Refactor of internal test framework to use fixtures for setup/teardown.

6.0.0
-----
* Major: Changed `DummyNet.bridge_set` API. `name` argument renamed to `bridge`.
* Major: Removed aliased function `DummyNet.bridge_up`, use `DummyNet.up`
  instead.
* Major: Refactor of most internal components to support `pytest-xdist`
  test parallelization.
  Interfaces, Namespaces, and CGroups now are prefixed with
  `d-XXXX-` internally. Old string based names are still functional, but require
  interface names to be at most 8 characters, compared to the previous 15.
* Patch: Add enforcement of Python 3.11 or later requirement in `setup.py`.

5.0.1
-----
* Patch: Resolved an issue in `DummyNet.link_list` where it previously caused a
  crash. The method now correctly returns a list of links as intended.

5.0.0
-----
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
