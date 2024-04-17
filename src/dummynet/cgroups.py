import subprocess

# TODO: - rewrite default path to cgroups
#       - add error handling
#       - Explore options of starting a process inside a cgroup
#       - Cgroup has 'namespace' module?
#       - Multiple cgroups or just one?
#       - Solve import issue in quick_start (see where to call this class)

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