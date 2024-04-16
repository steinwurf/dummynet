import dummynet
import logging
import os
import subprocess


class CgroupManager:
    def __init__(self, name):
        self.name = name

    def make_cgroup(self):
        """
        Create a cgroup with the specified name.

        Args:
            name (str): The name of the cgroup.

        Returns:
            None
        """
        subprocess.run(["sudo", "mkdir", f"/sys/fs/cgroup/{self.name}"])

    def delete_cgroup(self):
        """
        Delete the specified cgroup.

        Args:
            name (str): The name of the cgroup.

        Returns:
            None
        """
        subprocess.run(["sudo", "rmdir", f"/sys/fs/cgroup/{self.name}"])

    def add_cgroup_controller(self, controller):
        """
        Add a cgroup controller to a specific cgroup.

        Args:
            controller (str): The name of the cgroup controller.

        Example:
            add_cgroup_controller("my_cgroup", "cpu")
            # This will add the "cpu" controller to the "my_cgroup" cgroup.

        Returns:
            None
        """
        with open("/sys/fs/cgroup/cgroup.subtree_control", "w") as f:
            f.write(f"+{controller}")

    def add_to_cgroup(self, pid):
        """
        Add a process to the specified cgroup.

        Args:
            pid (int): The process ID.

        Returns:
            None
        """
        with open(f"/sys/fs/cgroup/{self.name}/cgroup.procs", "w") as f:
            f.write(f"{pid}")

    def set_cpu_limit(self, limit=0.5):
        """
        Set the CPU usage limit for a specific process in the cgroup.

        Args:
            pid (int): The process ID.
            limit (int): The CPU usage limit as a percentage.

        Returns:
            None
        """
        with open(f"/sys/fs/cgroup/{self.name}/cpu.max", "w") as f:
            f.write(f'{limit*100000} 100000')  # Convert limit to a percentage


# test = CgroupManager("test_group")
# test.add_cgroup_controller("cpu")
# test.add_to_cgroup(pid=42)
# test.set_cpu_limit()
# test.delete_cgroup()

def run():
    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)

    process_monitor = dummynet.ProcessMonitor(log=log)

    shell = dummynet.HostShell(log=log, sudo=True, process_monitor=process_monitor)

    net = dummynet.DummyNet(shell=shell)

    test_cgroup = CgroupManager("test_cgroup")

    try:

        # Get a list of the current namespaces
        namespaces = net.netns_list()
        assert namespaces == []

        # create two namespaces
        demo0 = net.netns_add(name="demo0")
        demo1 = net.netns_add(name="demo1")

        net.link_veth_add(p1_name="demo0-eth0", p2_name="demo1-eth0")

        # Move the interfaces to the namespaces
        net.link_set(namespace="demo0", interface="demo0-eth0")
        net.link_set(namespace="demo1", interface="demo1-eth0")

        # Bind an IP-address to the two peers in the link.
        demo0.addr_add(ip="10.0.0.1/24", interface="demo0-eth0")
        demo1.addr_add(ip="10.0.0.2/24", interface="demo1-eth0")

        # Activate the interfaces.
        demo0.up(interface="demo0-eth0")
        demo1.up(interface="demo1-eth0")
        demo0.up(interface="lo")
        demo1.up(interface="lo")

        # Test will run until last non-daemon process is done.
        proc0 = demo0.run_async(cmd="ping -c 20 10.0.0.2", daemon=True)
        proc1 = demo1.run_async(cmd="ping -c 10 10.0.0.1")


        test_cgroup.make_cgroup()
        test_cgroup.add_cgroup_controller("cpu")
        test_cgroup.add_to_cgroup(pid=proc0.pid)
        test_cgroup.add_to_cgroup(pid=proc1.pid)
        test_cgroup.set_cpu_limit(limit=0.5)

        # Print output as we go (optional)
        def _proc0_stdout(data):
            print("proc0: {}".format(data))

        def _proc1_stdout(data):
            print("proc1: {}".format(data))

        proc0.stdout_callback = _proc0_stdout
        proc1.stdout_callback = _proc1_stdout

        while process_monitor.run():
            pass

        # Check that the ping succeeded.
        proc1.match(stdout="10 packets transmitted*", stderr=None)

        # Since proc0 is a daemon we automatically kill it when the last
        # non-daemon process is done. However we can still see the output it
        # generated.
        print(f"proc0: {proc0.stdout}")

    finally:

        # Clean up.
        net.cleanup()


if __name__ == "__main__":
    run()
