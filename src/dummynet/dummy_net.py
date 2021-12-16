import re
from subprocess import CalledProcessError
from . import namespace_shell


class DummyNet(object):
    def __init__(self, shell):
        self.shell = shell

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

    def link_list(self):
        """Returns the output of the 'ip link list' command parsed to a
        list of strings"""

        output = self.shell.run(cmd="ip link list", cwd=None)

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

    def run(self, cmd, cwd=None):
        """Wrapper for the command-line access"""

        return self.shell.run(cmd=cmd, cwd=cwd)

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

    def netns_delete(self, name):
        """Deletes a specific network namespace."""

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
        return DummyNet(shell=shell)

    def open(self):
        if hasattr(self.shell, "open"):
            self.shell.open()

    def close(self):
        if hasattr(self.shell, "close"):
            self.shell.close()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, type, value, traceback):
        self.close()
