import os
import subprocess

# TODO:
#       - pass logger in instead of prints -> It doesn't do anything? !Explore! -> DONE
#       - debugger in namespace -> ?
#       - Use shell as argument to CgroupManager -> DONE
#       - Restructure the code, add args to CgroupManager init (controllers, limits, etc.) -> DONE
#       - Add more cgroup controllers (memory, io, etc.) -> Make a dict like; controller: "limit_value"
#       - Add more cgroup functionality (put whole script under a cgroup, more granular control, etc.) -> Find a way to delete cgroup when script is done --> DONE
#       - Add a way to say what to limit by how much (e.g. limit all processes in cgroup to 50% CPU, limit process 1 to 20% CPU, etc.)
#       - update NEWS.rst
#       - Add tests -> /waf build --run_tests | explore pytest and how to run tests from /tests
#       - Add CgroupManager to the documentation with an example
#       - Release and be happy.


class CgroupManager:
    """
    A class for managing cgroups.

    Args:
        name (str): The name of the cgroup.
        shell: The shell object used for executing shell commands.
        log: The log object used for logging messages.
        default_path (str, optional): The default path for cgroups. Defaults to "/sys/fs/cgroup".
        make_cgroup (bool, optional): Whether to create the cgroup. Defaults to True.
        controllers (Union[str, List[str]], optional): The cgroup controllers to add. Can be a string or a list of strings. Defaults to ["cpu"].
        limit (float, optional): The CPU usage limit for a specific process in the cgroup. Defaults to 0.5.
        limit_all (bool, optional): Whether to set the CPU limit for all processes in the cgroup. Defaults to True.

    Methods:
        make_cgroup(): Create a cgroup with the specified name.
        delete_cgroup(): Delete the specified cgroup.
        add_cgroup_controller(): Add a cgroup controller to the cgroup.
        add_to_cgroup(pid): Add a process to the specified cgroup.
        set_cpu_limit(): Set the CPU usage limit for a specific process in the cgroup.
    """

    def __init__(self, name: str, shell, log, default_path: str = "/sys/fs/cgroup", make_cgroup=True, controllers=["cpu"], limit=0.5, pid=None):
        self.name = name
        self.shell = shell
        self.log = log
        self.controllers = controllers
        self.limit = limit
        self.pid = pid
        self.default_path = default_path
        self.cgroup_pth = os.path.join(self.default_path, self.name)

        # Initial clean-up
        self.delete_cgroup()

        if make_cgroup:
            self.make_cgroup()

        self.add_cgroup_controller()
        self.set_cpu_limit()

        # Controll full script with pid = os.getpid()
        if self.pid:
            self.add_to_cgroup(self.pid)

    def make_cgroup(self):
        """
        Create a cgroup with the specified name.

        Returns:
            None
        """
        if os.path.exists(self.cgroup_pth):
            self.log.info(f"\nCgroup {self.name} already exists. Skipping creation.")        
        else:
            self.shell.run(cmd=f"mkdir {self.cgroup_pth}")
            self.log.info(f"\nCgroup {self.name} created.")


    def delete_cgroup(self):
        """
        Delete the specified cgroup.

        Returns:
            None
        """
        # Figure out how to catch error with self.shell?
        try:
            subprocess.run(["rmdir", self.cgroup_pth])
        except subprocess.CalledProcessError as e:
            self.log.info(f"Error: {e}\nContinuing...")
        finally:
            self.log.info(f"\nCgroup {self.name} deleted.")

    def add_cgroup_controller(self):
        """
        Add a cgroup controller to the cgroup.

        Returns:
            None
        """
        if isinstance(self.controllers, str):
            self.controllers = [self.controllers]

        for controller in self.controllers:
            self.shell.run(cmd=f"echo +'{controller}' > {self.default_path}/cgroup.subtree_control")

    def add_to_cgroup(self, pid):
        """
        Add a process to the specified cgroup.

        Args:
            pid (int): The process ID.

        Returns:
            None
        """
        if isinstance(pid, int):
            pid = [pid]
        for p in pid:
            self.shell.run(cmd=f"echo {p} > {self.cgroup_pth}/cgroup.procs")

    def set_cpu_limit(self):
        """
        Set the CPU usage limit for a specific process in the cgroup.

        Returns:
            None
        """
        assert 0 < self.limit <= 1, "Limit must be in range (0, 1]."

        self.shell.run(cmd=f"echo '{int(self.limit*100000)} 100000' > {self.cgroup_pth}/cpu.max")



# if __name__ == "__main__":
#     shell = dummynet.HostShell(log=log, sudo=True)
#     log = logging.getLogger("dummynet")
#     log.setLevel(logging.DEBUG)

#     test = CgroupManager("test_group", shell, log=log)
#     test.add_cgroup_controller(["cpu"])
#     # test.add_to_cgroup(pid=48820)
#     # test.set_cpu_limit()
#     # test.delete_cgroup()
