import dummynet
import logging
import os
import subprocess


def make_cgroup(name):
    """
    Create a cgroup with the specified name.

    Args:
        name (str): The name of the cgroup.

    Returns:
        None

    """
    subprocess.run(["sudo", "mkdir", f"/sys/fs/cgroup/{name}"])
    return None

def delete_cgroup(name):
    """
    Delete the specified cgroup.

    Args:
        name (str): The name of the cgroup.

    Returns:
        None

    """
    subprocess.run(["sudo", "rmdir", f"/sys/fs/cgroup/{name}"])
    return None

def add_cgroup_controller(name, controller):
    """
    Add a cgroup controller to a specific cgroup.

    Args:
        name (str): The name of the cgroup.
        controller (str): The name of the cgroup controller.

    Example:
        add_cgroup_controller("my_cgroup", "cpu")
        # This will add the "cpu" controller to the "my_cgroup" cgroup.

    Returns:
        None

    """
    subprocess.run(["sudo", "echo", f"'+{controller}'", ">", "/sys/fs/cgroup/cgroup.subtree_control"])
    return None

def add_to_cgroup(name, pid):
    """
    Add a process to the specified cgroup.

    Args:
        name (str): The name of the cgroup.
        pid (int): The process ID.

    Returns:
        None

    """
    subprocess.run(["sudo", "echo", f"{pid}", f"/sys/fs/cgroup/{name}/cgroup.procs"])
    return None



def run():
    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)

    process_monitor = dummynet.ProcessMonitor(log=log)

    shell = dummynet.HostShell(log=log, sudo=True, process_monitor=process_monitor)

    net = dummynet.DummyNet(shell=shell)

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
    # Get the current process ID
    pyscript_pid = os.getpid()
    print("PID:", pyscript_pid)
    # make_cgroup("test")    
    add_cgroup_controller("test", "cpu")    
    
    # run()

# TODO: - Fix add controller function
#       - Add process to cgroup
#       - Delete cgroup 
#       - Explore options of starting a process inside a cgroup
#       - Cgroup has 'namespace' module?
#       - Multiple cgroups or just one?