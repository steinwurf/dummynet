import re
from subprocess import CalledProcessError
from . import namespace_shell


class DummyNet(object):
    def __init__(self, shell):
        self.shell = shell
        self.cleaners = []

    def link_veth_add(self, p1_name, p2_name):
        """Adds a virtual ethernet between two endpoints.

        Name of the link will be 'p1_name@p2_name' when you look at 'ip addr'
        in the terminal"""

        self.shell.run(
            cmd=f"ip link add {p1_name} type veth peer name {p2_name}", cwd=None
        )

    def link_set(self, namespace, interface):
        """Binds a network interface (usually the veths) to a namespace.

        The namespace parameter is the name of the namespace as a string"""

        self.shell.run(cmd=f"ip link set {interface} netns {namespace}", cwd=None)

    def link_list(self, link_type=None):
        """Returns the output of the 'ip link list' command parsed to a
        list of strings"""

        cmd = "ip link list"

        if link_type != None:
            cmd += f" type {link_type}"

        output = self.shell.run(cmd=cmd, cwd=None)

        parser = re.compile(
            """
            \d+             # Match one or more digits
            :               # Followed by a colon
            \s              # Followed by a space
            (?P<name>[^:@]+)# Match all but : or @ (group "name")
            [:@]            # Followed by : or @
            .               # Followed by anything :)
        """,
            re.VERBOSE,
        )

        names = []

        for line in output.splitlines():
            # The name is the first word followed by a space
            result = parser.match(line)

            if result == None:
                continue

            names.append(result.group("name"))

        names.sort()
        return names

    def link_delete(self, interface):
        """Deletes a specific network interface."""

        self.shell.run(cmd=f"ip link delete {interface}", cwd=None)

    def addr_add(self, ip, interface):
        """Adds an IP-address to a network interface."""

        self.shell.run(f"ip addr add {ip} dev {interface}", cwd=None)

    def up(self, interface):
        """Sets the given network interface to 'up'"""

        self.shell.run(f"ip link set dev {interface} up", cwd=None)

    def route(self, ip):
        """Sets a new default IP-route."""

        self.shell.run(f"ip route add default via {ip}", cwd=None)

    def run(self, cmd, cwd=None, detach=False):
        """Wrapper for the command-line access"""

        return self.shell.run(cmd=cmd, cwd=cwd, detach=detach)

    async def run_async(self, cmd, daemon=False, delay=0, cwd=None):
        """Wrapper for the concurrent command-line access"""

        await self.shell.run_async(cmd=cmd, daemon=daemon, delay=delay, cwd=cwd)

    def tc_show(self, interface, cwd=None):
        """Shows the current traffic-control configurations in the given
        interface"""

        try:
            output = self.shell.run(cmd=f"tc qdisc show dev {interface}", cwd=cwd)
        except CalledProcessError as e:
            if e.stderr == 'exec of "tc" failed: No such file or directory\n':
                try:
                    output = self.shell.run(
                        cmd=f"/usr/sbin/tc qdisc show dev {interface}", cwd=cwd
                    )

                except CalledProcessError:
                    raise
            else:
                raise

        return output

    def tc(self, interface, delay=None, loss=None, rate=None, limit=None, cwd=None):
        """Modifies the given interface by adding any artificial combination of
        delay, packet loss, bandwidth constraints or queue limits"""

        extra_command = ""

        output = self.tc_show(interface=interface, cwd=cwd)

        if "netem" in output:
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
        except CalledProcessError as e:
            if e.stderr == 'exec of "tc" failed: No such file or directory\n':
                try:
                    extra_command += "/usr/sbin/"
                    self.shell.run(cmd=extra_command + cmd, cwd=cwd)

                except CalledProcessError:
                    raise
            else:
                raise

    def forward(self, from_interface, to_interface):
        """Forwards all traffic from one network interface to another."""
        self.shell.run(
            f"iptables -A FORWARD -o {from_interface} -i {to_interface} -j ACCEPT",
            cwd=None,
        )

    def nat(self, ip, interface):
        extra_command = ""
        cmd = f"iptables -t nat -A POSTROUTING -s {ip} -o {interface} -j MASQUERADE"
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

    def netns_list(self):
        """Returns a list of all network namespaces. Runs 'ip netns list'"""

        output = self.shell.run(cmd="ip netns list", cwd=None)
        names = []

        for line in output.splitlines():
            # The name is the first word followed by a space
            name = line.split(" ")[0]
            names.append(name)

        return names

    def netns_process_list(self, name):
        """Returns a list of all processes in a network namespace"""
        process_list = self.shell.run(cmd=f"ip netns pids {name}", cwd=None)
        return process_list.splitlines()

    def netns_kill_process(self, name, pid):
        """Kills a process in a network namespace"""
        self.shell.run(cmd=f"ip netns exec {name} kill -9 {pid}", cwd=None)

    def netns_kill_all(self, name):
        """Kills all processes running in a network namespace"""

        for process in self.netns_process_list(name):
            self.netns_kill_process(name, process)

    def netns_delete(self, name):
        """Deletes a specific network namespace.
        Note that before deleting a network namespace all processes in that
        namespace should be killed. Using e.g.

        process_list = shell.netns_get_process_list(ns_name).splitlines()
        for process in process_list:
            self.netns_kill_process(name, process)

        """

        self.shell.run(cmd=f"ip netns delete {name}", cwd=None)

    def netns_add(self, name):
        """Adds a new network namespace.

        Returns a new DummyNet object with a NamespaceShell, a wrapper to the
        command-line but with every command prefixed by 'ip netns exec name'
        This returned object is the main component for creating a dummy-network.
        Configuring these namespaces with the other utility commands allows you
        to configure the networks."""

        self.shell.run(cmd=f"ip netns add {name}", cwd=None)
        shell = namespace_shell.NamespaceShell(name=name, shell=self.shell)

        dnet = DummyNet(shell=shell)

        # Store cleanup function to remove the created namespace
        def cleaner():
            self.netns_kill_all(name=name)
            self.netns_delete(name=name)
            dnet.cleanup()

        self.cleaners.append(cleaner)

        return dnet

    def bridge_add(self, name):
        """Adds a bridge"""
        self.shell.run(cmd=f"ip link add name {name} type bridge", cwd=None)

    def bridge_up(self, name):
        """Brings a bridge up"""
        self.up(interface=name)

    def bridge_set(self, name, interface):
        """Adds an interface to a bridge"""
        self.shell.run(cmd=f"ip link set {interface} master {name}", cwd=None)

    def bridge_list(self):
        """List the different bridges"""
        return self.link_list(link_type="bridge")

    def cleanup(self):
        """Cleans up all the created network namespaces and bridges"""

        for cleaner in self.cleaners:
            cleaner()

