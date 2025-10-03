import re
from subprocess import CalledProcessError
from typing import Self
from logging import Logger

from dataclasses import dataclass, field

from dummynet.cgroups import CGroup
from dummynet.namespace_shell import NamespaceShell
from dummynet.host_shell import HostShell
from dummynet.run_info import RunInfo
from dummynet.scoped import (
    CGroupScoped,
    NamespaceScoped,
    InterfaceScoped,
)

ShellType = NamespaceShell | HostShell


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
    cgroups: list = field(default_factory=list)
    cleaners: list = field(default_factory=list)

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

        self.shell.run(
            cmd=f"ip link add {p1.scoped} type veth peer name {p2.scoped}",
            cwd=None,
        )

        return p1, p2

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

        self.shell.run(
            cmd=f"ip link set {interface.scoped} netns {namespace.scoped}",
            cwd=None,
        )

    def link_list(self, link_type=None) -> list[InterfaceScoped]:
        """Returns the output of the 'ip link list' command parsed to a
        list of strings

        :param link_type: The type of link to list (e.g. veth or bridge)
        :return: A list of interfaces of the links
        """

        cmd = "ip link list"

        if link_type is not None:
            cmd += f" type {link_type}"

        output = self.shell.run(cmd=cmd, cwd=None)

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

        self.shell.run(cmd=f"ip link delete {interface.scoped}", cwd=None)

    def addr_add(self, ip: str, interface: InterfaceScoped | str) -> None:
        """Adds an IP-address to a network interface."""

        interface = InterfaceScoped.from_any(interface)

        self.shell.run(f"ip addr add {ip} dev {interface.scoped}", cwd=None)

    def up(self, interface: InterfaceScoped | str) -> None:
        """Sets the given network device to 'up'"""

        interface = InterfaceScoped.from_any(interface)

        self.shell.run(f"ip link set dev {interface.scoped} up", cwd=None)

    def down(self, interface: InterfaceScoped | str) -> None:
        """Sets the given network device to 'down'"""

        interface = InterfaceScoped.from_any(interface)

        self.shell.run(f"ip link set dev {interface.scoped} down", cwd=None)

    def route(self, ip: str) -> None:
        """Sets a new default IP-route."""

        self.shell.run(f"ip route add default via {ip}", cwd=None)

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
            output = self.shell.run(
                cmd=f"tc qdisc show dev {interface.scoped}", cwd=cwd
            )
        # TODO: Do not reimplement our own PATH subset.
        except CalledProcessError as e:
            if e.stderr == 'exec of "tc" failed: No such file or directory\n':
                try:
                    output = self.shell.run(
                        cmd=f"/usr/sbin/tc qdisc show dev {interface.scoped}",
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

        cmd = f"tc qdisc {action} dev {interface.scoped} root netem"
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
            f"iptables -A FORWARD -o {from_interface.scoped} -i {to_interface.scoped} -j ACCEPT",
            cwd=None,
        )

    def nat(self, ip: str, interface: InterfaceScoped | str) -> None:
        interface = InterfaceScoped.from_any(interface)

        extra_command = ""
        cmd = f"iptables -t nat -A POSTROUTING -s {ip} -o {interface.scoped} -j MASQUERADE"
        # TODO: Do not reimplement our own PATH subset.
        try:
            self.shell.run(cmd=cmd, cwd=None)
        except CalledProcessError as e:
            if e.stderr == 'exec of "iptables" failed: No such file or directory\n':
                try:
                    extra_command += "/usr/sbin/"
                    self.shell.run(cmd=extra_command + cmd, cwd=None)

                except CalledProcessError:
                    raise
            else:
                raise

    def netns_list(self) -> list[NamespaceScoped]:
        """Returns a list of all network namespaces. Runs 'ip netns list'"""

        result = self.shell.run(cmd="ip netns list", cwd=None)
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

        result = self.shell.run(cmd=f"ip netns pids {namespace.scoped}", cwd=None)
        return result.stdout.splitlines()

    def netns_kill_process(self, namespace: NamespaceScoped | Self | str, pid: int):
        """Kills a process in a network namespace"""
        namespace = NamespaceScoped.from_any(namespace)

        self.shell.run(cmd=f"ip netns exec {namespace.scoped} kill -9 {pid}", cwd=None)

    def netns_kill_all(self, namespace: NamespaceScoped | Self | str):
        """Kills all processes running in a network namespace"""
        namespace = NamespaceScoped.from_any(namespace)

        for process in self.netns_process_list(namespace=namespace):
            try:
                self.netns_kill_process(namespace=namespace, pid=int(process))
            except Exception:
                self.shell.log.debug(
                    f"Failed to kill process {process} in {namespace.scoped}"
                )

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

        self.shell.run(cmd=f"ip netns delete {namespace.scoped}", cwd=None)

    def netns_add(self, name: str) -> Self:
        """Adds a new network namespace.

        Returns a new DummyNet object with a NamespaceShell, a wrapper to the
        command-line but with every command prefixed by 'ip netns exec name'
        This returned object is the main component for creating a dummy-network.
        Configuring these namespaces with the other utility commands allows you
        to configure the networks."""

        namespace = NamespaceScoped(name=name, uid=self.namespace.uid)

        self.shell.run(cmd=f"ip netns add {namespace.scoped}", cwd=None)

        # NOTE: Bad architecture, ideally we should not return a split-responsibility instance of itself
        ns_shell = NamespaceShell(name=namespace.scoped, shell=self.shell)
        dnet = self.__class__(shell=ns_shell, namespace=namespace)

        # Store cleanup function to remove the created namespace
        def cleaner():
            self.netns_kill_all(namespace)
            self.netns_delete(namespace)
            dnet.cleanup()

        self.cleaners.append(cleaner)

        return dnet

    def bridge_add(self, name: str) -> InterfaceScoped:
        """Adds a bridge"""
        bridge = InterfaceScoped(name=name, uid=self.namespace.uid)
        self.shell.run(cmd=f"ip link add name {bridge.scoped} type bridge", cwd=None)

        # def cleaner():
        #    self.shell.run(cmd=f"ip link del {bridge.scoped}", cwd=None)
        # self.cleaners.append(cleaner)

        return bridge

    def bridge_set(
        self, bridge: InterfaceScoped | str, interface: InterfaceScoped | str
    ) -> None:
        """Adds an interface to a bridge"""

        interface = InterfaceScoped.from_any(interface)
        bridge = InterfaceScoped.from_any(bridge)

        self.shell.run(
            cmd=f"ip link set {interface.scoped} master {bridge.scoped}",
            cwd=None,
        )

    def bridge_list(self) -> list[InterfaceScoped]:
        """List the different bridges"""
        return self.link_list(link_type="bridge")

    def cleanup(self) -> None:
        """Cleans up all the created network namespaces and bridges"""

        for cleaner in self.cleaners:
            cleaner()
        self.cleaners = []

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
        cgroup = CGroup(
            name=CGroupScoped(name=name, uid=self.namespace.uid).scoped,
            shell=shell,
            log=log,
            cpu_limit=cpu_limit,
            memory_limit=memory_limit,
        )
        self.cgroups.append(cgroup)
        self.cleaners.append(cgroup.hard_clean)
        return cgroup

    def cgroup_cleanup(self) -> None:
        """Cleans up all the created cgroups."""
        for c in self.cgroups:
            c.hard_clean()
        self.cgroups = []
