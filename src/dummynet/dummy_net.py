import re
from subprocess import CalledProcessError
from typing import Callable, NamedTuple, Self, List
from logging import Logger

from collections import OrderedDict
from dataclasses import dataclass, field

from dummynet.cgroups import CGroup
from dummynet.namespace_shell import NamespaceShell
from dummynet.host_shell import HostShell
from dummynet.run_info import RunInfo
from dummynet.scoped import (
    CGroupScoped,
    NamespaceScoped,
    InterfaceScoped,
    Scoped,
)

ShellType = NamespaceShell | HostShell


class CleanupItem(NamedTuple):
    namespace: NamespaceScoped
    target: Scoped
    reason: str
    cleaner: Callable


cleaners: List[CleanupItem] = []


@dataclass
class DummyNet:
    """A DummyNet object is used to create a network of virtual ethernet
    devices and bind them to namespaces.
    """

    shell: ShellType
    namespace: NamespaceScoped = field(
        # Root namespace under linux is simply called "1".
        default_factory=lambda: NamespaceScoped(name="1")
    )
    cgroups: OrderedDict[CGroupScoped, CGroup] = field(default_factory=OrderedDict)
    namespaces: OrderedDict[NamespaceScoped, Self] = field(default_factory=OrderedDict)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.cleanup()

    def link_veth_add(self, p1_name: str, p2_name: str) -> tuple[InterfaceScoped, InterfaceScoped]:
        """Adds a virtual ethernet between two endpoints.

        Name of the link will be 'p1_name@p2_name' when you look at 'ip addr'
        in the terminal

        :param p1_name: Name of the first endpoint
        :param p2_name: Name of the second endpoint
        :returns: A 2-tuple of ``p1_name`` and ``p2_name`` as interfaces
        """

        p1 = InterfaceScoped(name=p1_name)
        p2 = InterfaceScoped(name=p2_name)

        self.shell.run(
            cmd=f"ip link add {p1} type veth peer name {p2}",
        )

        # We only need to track one part of the veth, as deleting one destroys the other.
        # TODO: Find a cleaner solution given veth pairs, as its so easy to delete
        # another namespace first and break this cleaner.
        def cleaner():
            self.shell.run(
                cmd=f"ip link del {p1}",
            )

        cleaners.append(CleanupItem(self.namespace, p1, "link_veth_add", cleaner))

        return p1, p2

    def link_vlan_add(
        self, parent_interface: InterfaceScoped | str, vlan_id: int
    ) -> InterfaceScoped:
        """Add a VLAN subinterface to a parent interface.

        :param parent_interface: The parent interface to create a vlan from
        :param vlan_id: The numeric identifier of the vlan to add the interface to
        """

        parent_interface = InterfaceScoped.from_any(parent_interface)
        interface = InterfaceScoped(f"{parent_interface.name}.{vlan_id}")

        self.shell.run(
            cmd=f"ip link add link {parent_interface} name {interface} type vlan id {vlan_id}",
        )

        def cleaner():
            self.shell.run(
                cmd=f"ip link del {interface} || echo 'Already deleted, continuing...'",
            )

        cleaners.append(CleanupItem(self.namespace, interface, "link_vlan_add", cleaner))

        return interface

    def link_set(
        self, namespace: NamespaceScoped | Self | str, interface: InterfaceScoped | str
    ) -> None:
        """Binds a network interface (usually the veths) to a namespace.

        The namespace parameter is the name of the namespace as a string

        :param namespace: The namespace to bind the interface to
        :param interface: The interface to bind to the namespace
        """

        namespace = NamespaceScoped.from_any(namespace)
        interface = InterfaceScoped.from_any(interface)

        if namespace not in self.namespaces:
            raise ValueError(f"No such namespace: {namespace!r}")

        self.shell.run(
            cmd=f"ip link set {interface} netns {namespace}",
        )

        def cleaner():
            self.shell.run(
                cmd=f"ip netns exec {namespace} ip link set {interface} netns {self.namespace}",
            )

        cleaners.append(CleanupItem(namespace, interface, "link_set", cleaner))

    def link_list(self, link_type=None) -> list[InterfaceScoped]:
        """Returns the output of the 'ip link list' command parsed to a
        list of strings

        :param link_type: The type of link to list (e.g. veth or bridge)
        :return: A list of interfaces of the links
        """

        cmd = "ip link list"

        if link_type is not None:
            cmd += f" type {link_type}"

        output = self.shell.run(cmd=cmd)

        parser = re.compile(
            r"""
            \d+             # Match one or more digits
            :               # Followed by a colon
            \s              # Followed by a space
            (?P<name>[^:@]+)# Match all but : or @ (group "name")
            [:@]            # Followed by : or @
            .               # Followed by anything :)
            """,
            re.VERBOSE,
        )

        names: list[InterfaceScoped] = []

        for line in output.stdout.splitlines():
            # The name is the first word followed by a space
            result = parser.match(line)

            if result is None:
                continue

            try:
                name = InterfaceScoped.from_scoped(result.group("name"))
                if name.uid == self.namespace.uid:
                    names.append(name)
            except ValueError:
                continue

        return sorted(names)

    def link_delete(self, interface: InterfaceScoped | str) -> None:
        """Deletes a specific network interface."""

        interface = InterfaceScoped.from_any(interface)

        self.shell.run(cmd=f"ip link delete {interface}")

        # WARN: Dangerous! We cannot rely on cleaners of interface anymore!
        # WARN: Veths cannot be trusted anymore, p2 is never tracked.

    def addr_add(self, ip: str, interface: InterfaceScoped | str) -> None:
        """Adds an IP-address to a network interface."""

        interface = InterfaceScoped.from_any(interface)

        self.shell.run(f"ip addr add {ip} dev {interface}")

        def cleaner():
            self.shell.run(
                cmd=f"ip addr del {ip} dev {interface}",
            )

        cleaners.append(CleanupItem(self.namespace, interface, "addr_add", cleaner))

    def addr_del(self, ip: str, interface: InterfaceScoped | str) -> None:
        """Deletes an IP-address to a network interface."""

        interface = InterfaceScoped.from_any(interface)

        self.shell.run(f"ip addr del {ip} dev {interface}")

        def cleaner():
            self.shell.run(cmd=f"ip addr add {ip} dev {interface}")

        cleaners.append(CleanupItem(self.namespace, interface, "addr_del", cleaner))

    def up(self, interface: InterfaceScoped | str) -> None:
        """Sets the given network device to 'up'"""

        interface = InterfaceScoped.from_any(interface)

        self.shell.run(f"ip link set dev {interface} up")

        # WARN: Assumption, previous state was the opposite
        def cleaner():
            self.shell.run(cmd=f"ip link set dev {interface} down")

        cleaners.append(CleanupItem(self.namespace, interface, "up", cleaner))

    def down(self, interface: InterfaceScoped | str) -> None:
        """Sets the given network device to 'down'"""

        interface = InterfaceScoped.from_any(interface)

        self.shell.run(f"ip link set dev {interface} down")

        # WARN: Assumption, previous state was the opposite
        def cleaner():
            self.shell.run(cmd=f"ip link set dev {interface} up")

        cleaners.append(CleanupItem(self.namespace, interface, "down", cleaner))

    def route(self, ip: str) -> None:
        """Sets a new default IP-route."""

        self.shell.run(f"ip route add default via {ip}")

        # WARN: Assumption, previous state was the opposite
        def cleaner():
            self.shell.run(cmd=f"ip route del default via {ip}")

        cleaners.append(CleanupItem(self.namespace, InterfaceScoped(name="1"), "route", cleaner))

    def run(self, cmd: str, cwd=None) -> RunInfo:
        """Wrapper for the command-line access

        :param cmd: The command to run
        :param cwd: The working directory to run the command in
        """

        return self.shell.run(cmd=cmd, cwd=cwd)

    def run_async(self, cmd: str, daemon=False, cwd=None) -> RunInfo:
        """Wrapper for the concurrent command-line access

        Asynchronous commands run in the background. The process is launched via
        the shell.

        :param cmd: The command to run
        :param daemon: Whether to run the command as a daemon
        :param cwd: The working directory to run the command in
        """

        return self.shell.run_async(cmd=cmd, daemon=daemon, cwd=cwd)

    def tc_show(self, interface: InterfaceScoped | str, cwd=None):
        """Shows the current traffic-control configurations in the given
        interface"""

        interface = InterfaceScoped.from_any(interface)

        try:
            output = self.shell.run(cmd=f"tc qdisc show dev {interface}", cwd=cwd)
        # TODO: Do not reimplement our own PATH subset.
        except CalledProcessError as e:
            if e.stderr == 'exec of "tc" failed: No such file or directory\n':
                try:
                    output = self.shell.run(
                        cmd=f"/usr/sbin/tc qdisc show dev {interface}",
                        cwd=cwd,
                    )

                except CalledProcessError:
                    raise
            else:
                raise

        return output

    def tc(
        self,
        interface: InterfaceScoped | str,
        delay=None,
        loss=None,
        rate=None,
        limit=None,
        cwd=None,
    ) -> None:
        """Modifies the given interface by adding any artificial combination of
        delay, packet loss, bandwidth constraints or queue limits"""

        interface = InterfaceScoped.from_any(interface)

        extra_command = ""

        output = self.tc_show(interface=interface, cwd=cwd)

        if "netem" in output.stdout:
            action = "change"

        else:
            action = "add"

        cmd = f"tc qdisc {action} dev {interface} root netem"
        if delay:
            cmd += f" delay {delay}ms"
        if loss:
            cmd += f" loss {loss}%"
        if rate:
            cmd += f" rate {rate}Mbit"
        if limit:
            cmd += f" limit {limit}"

        try:
            self.shell.run(cmd=cmd, cwd=cwd)
        # TODO: Do not reimplement our own PATH subset.
        except CalledProcessError as e:
            if e.stderr == 'exec of "tc" failed: No such file or directory\n':
                try:
                    extra_command += "/usr/sbin/"
                    self.shell.run(cmd=extra_command + cmd, cwd=cwd)

                except CalledProcessError:
                    raise
            else:
                raise

    def forward(
        self, from_interface: InterfaceScoped | str, to_interface: InterfaceScoped | str
    ) -> None:
        """Forwards all traffic from one network interface to another."""

        from_interface = InterfaceScoped.from_any(from_interface)
        to_interface = InterfaceScoped.from_any(to_interface)

        self.shell.run(
            f"iptables -A FORWARD -o {from_interface} -i {to_interface} -j ACCEPT",
        )

        # TODO: Cleaner

    def nat(self, ip: str, interface: InterfaceScoped | str) -> None:
        interface = InterfaceScoped.from_any(interface)

        extra_command = ""
        cmd = f"iptables -t nat -A POSTROUTING -s {ip} -o {interface} -j MASQUERADE"
        # TODO: Do not reimplement our own PATH subset.
        try:
            self.shell.run(cmd=cmd)
        except CalledProcessError as e:
            if e.stderr == 'exec of "iptables" failed: No such file or directory\n':
                try:
                    extra_command += "/usr/sbin/"
                    self.shell.run(cmd=extra_command + cmd)

                except CalledProcessError:
                    raise
            else:
                raise

        # TODO: Cleaner

    def netns_list(self) -> list[NamespaceScoped]:
        """Returns a list of all network namespaces. Runs 'ip netns list'"""

        result = self.shell.run(cmd="ip netns list")
        namespaces: list[NamespaceScoped] = []

        for line in result.stdout.splitlines():
            try:
                # The name is the first word followed by a space
                name = line.split(" ")[0]
                namespace = NamespaceScoped.from_scoped(name)
                if namespace.uid == self.namespace.uid:
                    namespaces.append(namespace)
            except ValueError:
                continue

        return namespaces

    def netns_process_list(self, namespace: NamespaceScoped | Self | str) -> list[str]:
        """Returns a list of all processes in a network namespace"""
        namespace = NamespaceScoped.from_any(namespace)

        result = self.shell.run(cmd=f"ip netns pids {namespace}")
        return result.stdout.splitlines()

    def netns_kill_process(self, namespace: NamespaceScoped | Self | str, pid: int):
        """Kills a process in a network namespace"""
        namespace = NamespaceScoped.from_any(namespace)

        self.shell.run(cmd=f"ip netns exec {namespace} kill -9 {pid}")

    def netns_kill_all(self, namespace: NamespaceScoped | Self | str):
        """Kills all processes running in a network namespace"""
        namespace = NamespaceScoped.from_any(namespace)

        for process in self.netns_process_list(namespace=namespace):
            try:
                self.netns_kill_process(namespace=namespace, pid=int(process))
            except Exception:
                self.shell.log.debug(f"Failed to kill process {process} in {namespace}")

    def netns_delete(self, namespace: NamespaceScoped | Self | str):
        """Deletes a specific network namespace.
        Note that before deleting a network namespace all processes in that
        namespace should be killed. Using e.g.::

            process_list = net.netns_get_process_list(ns_name).splitlines()
            for process in process_list:
                self.netns_kill_process(name, process)

        :param name: The namespace to delete
        """
        namespace = NamespaceScoped.from_any(namespace)

        self.shell.run(cmd=f"ip netns delete {namespace}")

        # TODO: Cleaner?

    def netns_add(self, name: str) -> Self:
        """Adds a new network namespace.

        Returns a new DummyNet object with a NamespaceShell, a wrapper to the
        command-line but with every command prefixed by 'ip netns exec name'
        This returned object is the main component for creating a dummy-network.
        Configuring these namespaces with the other utility commands allows you
        to configure the networks."""

        namespace = NamespaceScoped(name=name, uid=self.namespace.uid)

        self.shell.run(cmd=f"ip netns add {namespace}")

        # NOTE: Bad architecture, ideally we should not return a split-responsibility instance of itself
        ns_shell = NamespaceShell(name=namespace.scoped, shell=self.shell)
        dnet = self.__class__(shell=ns_shell, namespace=namespace)
        self.namespaces[namespace] = dnet

        # Store cleanup function to remove the created namespace
        def cleaner():
            self.netns_kill_all(namespace)
            # dnet.cleanup() # our dnet should not have any cleanup needed.
            self.netns_delete(namespace)
            self.namespaces.pop(namespace)

        cleaners.append(CleanupItem(namespace, InterfaceScoped(name="1"), "netns_add", cleaner))

        return dnet

    def bridge_add(self, name: str) -> InterfaceScoped:
        """Adds a bridge"""
        bridge = InterfaceScoped(name=name, uid=self.namespace.uid)
        self.shell.run(cmd=f"ip link add name {bridge} type bridge")

        def cleaner():
            self.shell.run(cmd=f"ip link del {bridge}")

        cleaners.append(CleanupItem(self.namespace, bridge, "bridge_add", cleaner))

        return bridge

    def bridge_set(self, bridge: InterfaceScoped | str, interface: InterfaceScoped | str) -> None:
        """Adds an interface to a bridge"""

        interface = InterfaceScoped.from_any(interface)
        bridge = InterfaceScoped.from_any(bridge)

        self.shell.run(
            cmd=f"ip link set {interface} master {bridge}",
        )

        # TODO: Cleaner

    def bridge_list(self) -> list[InterfaceScoped]:
        """List the different bridges"""
        return self.link_list(link_type="bridge")

    def cleanup(self) -> None:
        """Cleans up all the created network namespaces and bridges"""

        # self.shell.log.debug(f"Running cleanup with items {cleaners!r}")

        while cleaners:
            namespace, target, reason, cleaner = cleaners.pop()
            self.shell.log.info(f"Running cleanup for {reason!r} by {target!r} in {namespace!r}")
            cleaner()

        assert not cleaners, f"cleanup: expected cleaners to be empty, got {cleaners!r}"
        assert not self.namespaces, (
            f"cleanup: expected namespaces to be empty, got {self.namespaces!r}"
        )
        assert not self.cgroups, f"cleanup: expected cgroups to be empty, got {self.cgroups!r}"

    def add_cgroup(
        self,
        name: str,
        shell: ShellType,
        log: Logger,
        cpu_limit: float | None = None,
        memory_limit: int | None = None,
    ) -> CGroup:
        """
        Creates a new cgroup object.

        :param name: The name of the cgroup.
        :param shell: The shell object used for executing shell commands.
        :param log: The log object used for logging messages.
        :param cpu_limit: The ratio of CPU usage limit for the cgroup. Between 0 and 1. Defaults to None.
        :param memory_limit: The memory usage hard-limit for the cgroup. In bytes. Defaults to None.
               if memory usage exceeds the limit, the processes will get killed by the kernel. OOM.

        :return: A CGroup object.
        """
        cgroup_scoped = CGroupScoped(name=name, uid=self.namespace.uid)
        cgroup = CGroup(
            name=cgroup_scoped.scoped,
            shell=shell,
            log=log,
            cpu_limit=cpu_limit,
            memory_limit=memory_limit,
        )
        self.cgroups[cgroup_scoped] = cgroup

        def cleaner():
            cgroup.hard_clean()
            self.cgroups.pop(cgroup_scoped)

        cleaners.append(CleanupItem(self.namespace, cgroup_scoped, "add_cgroup", cleaner))

        return cgroup

    def cgroup_list(self) -> list[CGroupScoped]:
        """Returns a list of all cgroups. Runs 'find /sys/fs/cgroup -maxdepth 1 -mindepth 1 -type d'"""

        result = self.shell.run(cmd="find /sys/fs/cgroup -maxdepth 1 -mindepth 1 -type d")
        cgroups: list[CGroupScoped] = []

        for line in result.stdout.splitlines():
            try:
                cgroup = CGroupScoped.from_scoped(line)
                if cgroup.uid == self.namespace.uid:
                    cgroups.append(cgroup)
            except ValueError:
                continue

        return cgroups
