import subprocess
import os


# TODO:
#       - Explore options of starting a process inside a cgroup
#       - Multiple cgroups or just one?
#       - pass logger in instead of prints
#       - debugger in namespce
#       - Use shell as argument to CgroupManager
#       - Restructure the code, add args to CgroupManager init (controllers, limits, etc.)
#       - Add more cgroup controllers (memory, io, etc.)
#       - Add more cgroup functionality (put whole script under a cgroup, more granular control, etc.)
#       - update NEWS.rst
#       - Add tests -> /waf build --run_tests | explore pytest and how to run tests from /tests
#       - Add CgroupManager to the documentation with an example
#       - Release and be happy.


class CgroupManager:
    """
    A class for managing cgroups.

    Args:
        name (str): The name of the cgroup.

    Methods:
        make_cgroup(): Create a cgroup with the specified name.
        delete_cgroup(): Delete the specified cgroup.
        add_cgroup_controller(controller): Add a cgroup controller to a specific cgroup.
        add_to_cgroup(pid): Add a process to the specified cgroup.
        set_cpu_limit(limit): Set the CPU usage limit for a specific process in the cgroup.
    """

    def __init__(self, name: str, default_path: str = "/sys/fs/cgroup"):
        self.name = name
        self.default_path = default_path

    def make_cgroup(self):
        """
        Create a cgroup with the specified name.

        Returns:
            None
        """
        if os.path.exists(os.path.join(self.default_path, self.name)):
            print(f"\nCgroup {self.name} already exists. Skipping creation.")        
        else:
            subprocess.run(["sudo", "mkdir", f"{self.default_path}/{self.name}"])
            print(f"\nCgroup {self.name} created.")


    def delete_cgroup(self):
        """
        Delete the specified cgroup.

        Returns:
            None
        """
        subprocess.run(["sudo", "rmdir", f"{self.default_path}/{self.name}"])
        if not os.path.exists(os.path.join(self.default_path, self.name)):
            print(f"Cgroup {self.name} deleted.")  

    def add_cgroup_controller(self, controller):
        """
        Add a cgroup controller to a specific cgroup.

        Args:
            controller (str): The name of the cgroup controller.

        Example:
            add_cgroup_controller("my_cgroup", "cpu")
            -> This will add the "cpu" controller to the "my_cgroup" cgroup.

        Returns:
            None
        """
        with open(f"{self.default_path}/cgroup.subtree_control", "r+") as f:
            if controller in f.read():
                print(f"\nController {controller} already exists in cgroup {self.name}. Skipping addition.")
            else:
                f.write(f"+{controller}")

    def add_to_cgroup(self, pid):
        """
        Add a process to the specified cgroup.

        Args:
            pid (int): The process ID.

        Returns:
            None
        """
        with open(f"{self.default_path}/{self.name}/cgroup.procs", "r+") as f:
            if str(pid) in f.read():
                print(f"\nProcess {pid} already exists in cgroup {self.name}. Skipping addition.")
            else:
                f.write(f"{pid}")

    def set_cpu_limit(self, limit=0.5):
        """
        Set the CPU usage limit for a specific process in the cgroup.

        Args:
            limit (int): The CPU usage limit as a percentage.

        Returns:
            None
        """
        with open(f"{self.default_path}/{self.name}/cpu.max", "w") as f:
            f.write(f'{limit*100000} 100000')  # Convert limit to a percentage


# test = CgroupManager("test_group")
# test.make_cgroup()
# test.add_cgroup_controller("cpu")
# test.add_to_cgroup(pid=48820)
# test.set_cpu_limit()
# test.delete_cgroup()
