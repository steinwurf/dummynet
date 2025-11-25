import re
import json
from subprocess import CalledProcessError
from typing import Callable, NamedTuple, Optional, Self, List
from logging import Logger

from collections import OrderedDict
from dataclasses import dataclass, field

from dummynet import errors
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
    cleaners: List[CleanupItem] = field(default_factory=list)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.cleanup()

    def link_veth_add(
        self, p1_name: str, p2_name: str
    ) -> tuple[InterfaceScoped, InterfaceScoped]:
        """Adds a virtual ethernet between two endpoints.

        Name of the link will be 'p1_name@p2_name' when you look at 'ip addr'
        in the terminal

        :param p1_name: Name of the first endpoint
        :param p2_name: Name of the second endpoint
        :returns: A 2-tuple of ``p1_name`` and ``p2_name`` as interfaces
        """

        p1 = InterfaceScoped(name=p1_name)
        p2 = InterfaceScoped(name=p2_name)

        self.shell.run(cmd=f"ip link add {p1} type veth peer name {p2}")

        self.shell.poll_until(
            f"ip -j link show dev {p1}", match_stdout=f'*"ifname":"{p1}"*'
        )

        # We only need to track one part of the veth, as deleting one destroys the other.
        # TODO: Find a cleaner solution given veth pairs, as its so easy to delete
        # another namespace first and break this cleaner.
        def cleaner():
            try:
                self.shell.run(cmd=f"ip link del {p1}")
            except errors.RunInfoError:
                self.shell.log.warning(
                    f"veth pair {p1!r} peer {p2!r} was already deleted?"
                )

        self.cleaners.append(CleanupItem(self.namespace, p1, "link_veth_add", cleaner))

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

        self.shell.poll_until(
            f"ip -j link show dev {interface}", match_stdout=f'*"ifname":"{interface}"*'
        )

        def cleaner():
            try:
                self.shell.run(cmd=f"ip link del {interface}")
            except errors.RunInfoError:
                self.shell.log.warning(f"vlan {interface!r} was already deleted?")

        self.cleaners.append(
            CleanupItem(self.namespace, interface, "link_vlan_add", cleaner)
        )

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

        self.shell.poll_until(
            f"ip netns exec {namespace} ip -j link show dev {interface}",
            match_stdout=f'*"ifname":"{interface}"*',
        )

        def cleaner():
            self.shell.run(
                cmd=f"ip netns exec {namespace} ip link set {interface} netns {self.namespace}",
            )

        self.cleaners.append(CleanupItem(namespace, interface, "link_set", cleaner))

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

        self.shell.poll_until(
            f"ip -j link show dev {interface}",
            match_stderr=f'*Device "{interface}" does not exist.*',
        )

        # We do not want to have the burden to recreate the link precicely, so
        # instead we remove all cleaners with the interface's name.
        # HACK: veths are not nicely handled since only one interface is tracked.
        self.cleaners[:] = [
            item for item in self.cleaners if not item.target == interface
        ]

    def addr_add(self, ip: str, interface: InterfaceScoped | str) -> None:
        """Adds an IP-address to a network interface."""

        interface = InterfaceScoped.from_any(interface)

        self.shell.run(f"ip addr add {ip} dev {interface}")

        self.shell.poll_until(f"ip addr show dev {interface}", match_stdout=f"*{ip}*")

        def cleaner():
            self.shell.run(
                cmd=f"ip addr del {ip} dev {interface}",
            )

        self.cleaners.append(
            CleanupItem(self.namespace, interface, "addr_add", cleaner)
        )

    def addr_del(self, ip: str, interface: InterfaceScoped | str) -> None:
        """Deletes an IP-address to a network interface."""

        interface = InterfaceScoped.from_any(interface)

        self.shell.run(f"ip addr del {ip} dev {interface}")

        def match_lambda(line):
            try:
                device = json.loads(line)[0]
            except json.JSONDecodeError:
                return False

            return not any(
                f"{addr['local']}/{addr['prefixlen']}" == ip or addr["local"] == ip
                for addr in device["addr_info"]
            )

        self.shell.poll_until(
            f"ip -j addr show dev {interface}",
            match_lambda=match_lambda,
        )

        def cleaner():
            self.shell.run(cmd=f"ip addr add {ip} dev {interface}")

        self.cleaners.append(
            CleanupItem(self.namespace, interface, "addr_del", cleaner)
        )

    def _current_administrative_state(
        self, interface: InterfaceScoped | str
    ) -> Optional[str]:
        interface = InterfaceScoped.from_any(interface)
        runinfo = self.shell.run(f"ip -j link show dev {interface}")
        try:
            device = json.loads(runinfo.stdout)[0]
        except json.JSONDecodeError:
            return None
        if "UP" in device["flags"]:
            return "up"
        else:
            return "down"

    def up(self, interface: InterfaceScoped | str) -> None:
        """Sets the given network device to 'up'"""

        interface = InterfaceScoped.from_any(interface)

        # NOTE: If device does not exist, assume opposite state.
        # TODO: Better checking for device existence.
        prev_state: str = self._current_administrative_state(interface) or "down"

        self.shell.run(f"ip link set dev {interface} up")

        def match_lambda(line):
            try:
                device = json.loads(line)[0]
            except json.JSONDecodeError:
                return False

            return "UP" in device["flags"]

        self.shell.poll_until(
            f"ip -j link show dev {interface}", match_lambda=match_lambda
        )

        def cleaner():
            self.shell.run(cmd=f"ip link set dev {interface} {prev_state}")

        self.cleaners.append(CleanupItem(self.namespace, interface, "up", cleaner))

    def down(self, interface: InterfaceScoped | str) -> None:
        """Sets the given network device to 'down'"""

        interface = InterfaceScoped.from_any(interface)

        # NOTE: If device does not exist, assume opposite state.
        # TODO: Better checking for device existence.
        prev_state: str = self._current_administrative_state(interface) or "up"

        self.shell.run(f"ip link set dev {interface} down")

        self.shell.poll_until(
            f"ip -j link show dev {interface}", match_stdout='*"operstate":"DOWN"*'
        )

        # WARN: Assumption, previous state was the opposite
        def cleaner():
            self.shell.run(cmd=f"ip link set dev {interface} {prev_state}")

        self.cleaners.append(CleanupItem(self.namespace, interface, "down", cleaner))

    def route(self, ip: str) -> None:
        """Sets a new default IP-route."""

        self.shell.run(f"ip route add default via {ip}")

        def match_lambda(line):
            addr = ip.split("/", 1)[0]

            try:
                routes = json.loads(line)
            except json.JSONDecodeError:
                return False

            return any(
                route["dst"] == "default" and route["gateway"] == addr
                for route in routes
            )

        self.shell.poll_until("ip -j route", match_lambda=match_lambda)

        # WARN: Assumption, previous state was the opposite
        def cleaner():
            try:
                self.shell.run(cmd=f"ip route del default via {ip}")
            except errors.RunInfoError:
                self.shell.log.warning(
                    f"Cannot remove default route via {ip!r}, did its device go down?"
                )

        self.cleaners.append(
            CleanupItem(self.namespace, InterfaceScoped(name="1"), "route", cleaner)
        )

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

        self.shell.run(cmd=cmd, cwd=cwd)

        # TODO: Poller?
        # TODO: Cleaner?

    def forward(
        self, from_interface: InterfaceScoped | str, to_interface: InterfaceScoped | str
    ) -> None:
        """Forwards all traffic from one network interface to another."""

        from_interface = InterfaceScoped.from_any(from_interface)
        to_interface = InterfaceScoped.from_any(to_interface)

        self.shell.run(
            f"iptables -A FORWARD -o {from_interface} -i {to_interface} -j ACCEPT",
        )

        # TODO: Poller

        def cleaner():
            self.shell.run(
                cmd=f"iptables -D FORWARD -o {from_interface} -i {to_interface} -j ACCEPT"
            )

        self.cleaners.append(
            CleanupItem(self.namespace, from_interface, "forward", cleaner)
        )

    def nat(self, ip: str, interface: InterfaceScoped | str) -> None:
        interface = InterfaceScoped.from_any(interface)

        self.shell.run(
            cmd=f"iptables -t nat -A POSTROUTING -s {ip} -o {interface} -j MASQUERADE"
        )

        # TODO: Poller

        def cleaner():
            self.shell.run(
                cmd=f"iptables -t nat -D POSTROUTING -s {ip} -o {interface} -j MASQUERADE"
            )

        self.cleaners.append(CleanupItem(self.namespace, interface, "nat", cleaner))

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

        self.cleaners[:] = [
            item for item in self.cleaners if not item.namespace == namespace
        ]

    def netns_add(self, name: str) -> Self:
        """Adds a new network namespace.

        Returns a new DummyNet object with a NamespaceShell, a wrapper to the
        command-line but with every command prefixed by 'ip netns exec name'
        This returned object is the main component for creating a dummy-network.
        Configuring these namespaces with the other utility commands allows you
        to configure the networks."""

        namespace = NamespaceScoped(name=name, uid=self.namespace.uid)

        self.shell.run(cmd=f"ip netns add {namespace}")

        # TODO: Poller

        # NOTE: Bad architecture, ideally we should not return a split-responsibility instance of itself
        ns_shell = NamespaceShell(name=namespace.scoped, shell=self.shell)
        dnet = self.__class__(
            shell=ns_shell, namespace=namespace, cleaners=self.cleaners
        )
        self.namespaces[namespace] = dnet

        # Store cleanup function to remove the created namespace
        def cleaner():
            self.netns_kill_all(namespace)
            # dnet.cleanup() # our dnet should not have any cleanup needed.
            self.netns_delete(namespace)
            self.namespaces.pop(namespace)

        self.cleaners.append(
            CleanupItem(namespace, InterfaceScoped(name="1"), "netns_add", cleaner)
        )

        return dnet

    def bridge_add(self, name: str) -> InterfaceScoped:
        """Adds a bridge"""
        bridge = InterfaceScoped(name=name, uid=self.namespace.uid)
        self.shell.run(cmd=f"ip link add name {bridge} type bridge")

        # TODO: Poller

        def cleaner():
            self.shell.run(cmd=f"ip link del {bridge}")

        self.cleaners.append(CleanupItem(self.namespace, bridge, "bridge_add", cleaner))

        return bridge

    def bridge_set(
        self, bridge: InterfaceScoped | str, interface: InterfaceScoped | str
    ) -> None:
        """Adds an interface to a bridge"""

        interface = InterfaceScoped.from_any(interface)
        bridge = InterfaceScoped.from_any(bridge)

        self.shell.run(cmd=f"ip link set {interface} master {bridge}")

        # TODO: Poller

        def cleaner():
            self.shell.run(cmd=f"ip link set {interface} nomaster")

        self.cleaners.append(
            CleanupItem(self.namespace, interface, "bridge_set", cleaner)
        )

    def bridge_list(self) -> list[InterfaceScoped]:
        """List the different bridges"""
        return self.link_list(link_type="bridge")

    def cleanup(self) -> None:
        """Cleans up all the created network namespaces and bridges"""

        # Clean up dangling processes.
        exceptions = None
        try:
            self.shell.process_monitor.stop()
        except ExceptionGroup as e:
            # Capture dangling error
            exceptions = e
            # Force cleanup for cleanup to still run.
            self.shell.process_monitor.stop(validate_state=False)

        while self.cleaners:
            namespace, target, reason, cleaner = self.cleaners.pop()
            self.shell.log.info(
                f"Running cleanup for {reason!r} by {target!r} in {namespace!r}"
            )
            cleaner()

        assert (
            not self.cleaners
        ), f"cleanup: expected cleaners to be empty, got {self.cleaners!r}"
        assert (
            not self.namespaces
        ), f"cleanup: expected namespaces to be empty, got {self.namespaces!r}"
        assert (
            not self.cgroups
        ), f"cleanup: expected cgroups to be empty, got {self.cgroups!r}"

        if exceptions:
            raise exceptions

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

        # TODO: Poller?

        def cleaner():
            cgroup.hard_clean()
            self.cgroups.pop(cgroup_scoped)

        self.cleaners.append(
            CleanupItem(self.namespace, cgroup_scoped, "add_cgroup", cleaner)
        )

        return cgroup

    def cgroup_list(self) -> list[CGroupScoped]:
        """Returns a list of all cgroups. Runs 'find /sys/fs/cgroup -maxdepth 1 -mindepth 1 -type d'"""

        result = self.shell.run(
            cmd="find /sys/fs/cgroup -maxdepth 1 -mindepth 1 -type d"
        )
        cgroups: list[CGroupScoped] = []

        for line in result.stdout.splitlines():
            try:
                cgroup = CGroupScoped.from_scoped(line)
                if cgroup.uid == self.namespace.uid:
                    cgroups.append(cgroup)
            except ValueError:
                continue

        return cgroups
