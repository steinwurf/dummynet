import re
import os
from subprocess import CalledProcessError, CompletedProcess
from . import namespace_shell
from dummynet.scopedname import (
    ScopedName,
    BridgeName,
    InterfaceName,
    NamespaceName,
    CGroupName,
)
from dummynet.cgroups import CGroup
from logging import Logger


class DummyNet:
    """A DummyNet object is used to create a network of virtual ethernet
    devices and bind them to namespaces.
    """

    def __init__(self, shell):
        """Creates a new DummyNet object.

        :param shell: The shell to use for running commands
        """
        self.shell = shell
        self.pid = os.getpid()
        self.cgroups = []
        self.cleaners = []

    def link_veth_add(
        self, p1_name: str, p2_name: str
    ) -> tuple[InterfaceName, InterfaceName]:
        """Adds a virtual ethernet between two endpoints.

        Name of the link will be 'p1_name@p2_name' when you look at 'ip addr'
        in the terminal

        :param p1_name: Name of the first endpoint
        :param p2_name: Name of the second endpoint
        """

        p1 = InterfaceName(p1_name)
        p2 = InterfaceName(p2_name)

        self.shell.run(
            cmd=f"ip link add {p1.scoped} type veth peer name {p2.scoped}",
            cwd=None,
        )

        return p1, p2

    def link_set(self, namespace: NamespaceName, interface: InterfaceName) -> None:
        """Binds a network interface (usually the veths) to a namespace.

        The namespace parameter is the name of the namespace as a string

        :param namespace: The namespace to bind the interface to
        :param interface: The interface to bind to the namespace
        """

        self.shell.run(
            cmd=f"ip link set {interface.scoped} netns {namespace.scoped}",
            cwd=None,
        )

    def link_list(self, link_type=None) -> list[InterfaceName]:
        """Returns the output of the 'ip link list' command parsed to a
        list of strings

        :param link_type: The type of link to list (e.g. veth or bridge)
        :return: A list of strings with the names of the links
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

        names: list[InterfaceName] = []

        for line in output.stdout.splitlines():
            # The name is the first word followed by a space
            result = parser.match(line)

            if result is None:
                continue

            names.append(InterfaceName.from_scoped(result.group("name")))

        return sorted(names)

    def link_delete(self, interface: InterfaceName) -> None:
        """Deletes a specific network interface."""

        self.shell.run(cmd=f"ip link delete {interface.scoped}", cwd=None)

    def addr_add(self, ip: str, interface: InterfaceName) -> None:
        """Adds an IP-address to a network interface."""

        self.shell.run(f"ip addr add {ip} dev {interface.scoped}", cwd=None)

    def up(self, device: ScopedName) -> None:
        """Sets the given network device to 'up'"""

        self.shell.run(f"ip link set dev {device.scoped} up", cwd=None)

    def route(self, ip: str) -> None:
        """Sets a new default IP-route."""

        self.shell.run(f"ip route add default via {ip}", cwd=None)

    def run(self, cmd, cwd=None):
        """Wrapper for the command-line access

        :param cmd: The command to run
        :param cwd: The working directory to run the command in
        :return: A :ref:`dummynetruninfo` object
        """

        return self.shell.run(cmd=cmd, cwd=cwd)

    def run_async(self, cmd, daemon=False, cwd=None):
        """Wrapper for the concurrent command-line access

        Asynchronous commands run in the background. The process is launched via
        the shell.

        :param cmd: The command to run
        :param daemon: Whether to run the command as a daemon
        :param cwd: The working directory to run the command in
        :return: A :ref:`dummynetruninfo` object
        """

        return self.shell.run_async(cmd=cmd, daemon=daemon, cwd=cwd)

    def tc_show(self, interface: InterfaceName, cwd=None) -> CompletedProcess:
        """Shows the current traffic-control configurations in the given
        interface"""

        try:
            output = self.shell.run(
                cmd=f"tc qdisc show dev {interface.scoped}", cwd=cwd
            )
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
        interface: InterfaceName,
        delay=None,
        loss=None,
        rate=None,
        limit=None,
        cwd=None,
    ) -> None:
        """Modifies the given interface by adding any artificial combination of
        delay, packet loss, bandwidth constraints or queue limits"""

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
        self, from_interface: InterfaceName, to_interface: InterfaceName
    ) -> None:
        """Forwards all traffic from one network interface to another."""
        self.shell.run(
            f"iptables -A FORWARD -o {from_interface.scoped} -i {to_interface.scoped} -j ACCEPT",
            cwd=None,
        )

    def nat(self, ip: str, interface: InterfaceName) -> None:
        extra_command = ""
        cmd = f"iptables -t nat -A POSTROUTING -s {ip} -o {interface.scoped} -j MASQUERADE"
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

    # TODO: Filter by process?
    def netns_list(self) -> list[NamespaceName]:
        """Returns a list of all network namespaces. Runs 'ip netns list'"""

        result = self.shell.run(cmd="ip netns list", cwd=None)
        names: list[NamespaceName] = []

        for line in result.stdout.splitlines():
            # The name is the first word followed by a space
            name = NamespaceName.from_scoped(line.split(" ")[0])
            if name.pid == self.pid:
                names.append(name)

        return sorted(names)

    # TODO: Maybe int return type?
    def netns_process_list(self, namespace: NamespaceName) -> list[str]:
        """Returns a list of all processes in a network namespace"""
        result = self.shell.run(cmd=f"ip netns pids {namespace.scoped}", cwd=None)
        return result.stdout.splitlines()

    def netns_kill_process(self, namespace: NamespaceName, pid: int):
        """Kills a process in a network namespace"""
        self.shell.run(cmd=f"ip netns exec {namespace.scoped} kill -9 {pid}", cwd=None)

    def netns_kill_all(self, namespace: NamespaceName):
        """Kills all processes running in a network namespace"""

        for process in self.netns_process_list(namespace=namespace):
            try:
                self.netns_kill_process(namespace=namespace, pid=int(process))
            except Exception:
                self.shell.log.debug(
                    f"Failed to kill process {process} in {namespace.scoped}"
                )

    def netns_delete(self, namespace: NamespaceName):
        """Deletes a specific network namespace.
        Note that before deleting a network namespace all processes in that
        namespace should be killed. Using e.g.::

            process_list = net.netns_get_process_list(ns_name).splitlines()
            for process in process_list:
                self.netns_kill_process(name, process)

        :param name: Name of the namespace to delete
        """

        self.shell.run(cmd=f"ip netns delete {namespace.scoped}", cwd=None)

    def netns_add(self, name: str) -> tuple[NamespaceName, "DummyNet"]:
        """Adds a new network namespace.

        Returns a new DummyNet object with a NamespaceShell, a wrapper to the
        command-line but with every command prefixed by 'ip netns exec name'
        This returned object is the main component for creating a dummy-network.
        Configuring these namespaces with the other utility commands allows you
        to configure the networks."""

        namespace = NamespaceName(name=name, pid=self.pid)

        self.shell.run(cmd=f"ip netns add {namespace.scoped}", cwd=None)

        # TODO: This is abusing DummyNet
        ns_shell = namespace_shell.NamespaceShell(
            name=namespace.scoped, shell=self.shell
        )
        dnet = self.__class__(shell=ns_shell)

        # Store cleanup function to remove the created namespace
        def cleaner():
            self.netns_kill_all(namespace)
            self.netns_delete(namespace)
            dnet.cleanup()

        self.cleaners.append(cleaner)

        return namespace, dnet

    def bridge_add(self, name: str) -> BridgeName:
        """Adds a bridge"""
        bridge = BridgeName(name=name, pid=self.pid)
        self.shell.run(cmd=f"ip link add name {bridge.scoped} type bridge", cwd=None)
        return bridge

    # TODO: This could be done with up directly?
    def bridge_up(self, bridge: BridgeName):
        """Brings a bridge up"""
        self.up(bridge)

    def bridge_set(self, bridge: BridgeName, interface: InterfaceName) -> None:
        """Adds an interface to a bridge"""
        self.shell.run(
            cmd=f"ip link set {interface.scoped} master {bridge.scoped}",
            cwd=None,
        )

    def bridge_list(self) -> list[BridgeName]:
        """List the different bridges"""
        # HACK: Is bridge an interface?
        return [
            BridgeName(name=interface.name, pid=interface.pid)
            for interface in self.link_list(link_type="bridge")
        ]

    def cleanup(self):
        """Cleans up all the created network namespaces and bridges"""

        for cleaner in self.cleaners:
            cleaner()

    # TODO: Rename to cgroup_add
    def add_cgroup(
        self,
        name: str,
        shell,
        log: Logger,
        cpu_limit=None,
        memory_limit=None,
    ):
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
            name=CGroupName(name, self.pid).scoped,
            shell=shell,
            log=log,
            cpu_limit=cpu_limit,
            memory_limit=memory_limit,
        )
        self.cgroups.append(cgroup)
        self.cleaners.append(cgroup.hard_clean)
        return cgroup

    def cgroup_cleanup(self):
        """Cleans up all the created cgroups."""
        for c in self.cgroups:
            c.hard_clean()
