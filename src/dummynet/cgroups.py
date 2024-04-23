import os
import logging
import subprocess

# TODO:
#       - pass logger in instead of prints -> It doesn't do anything? !Explore!
#       - debugger in namespace
#       - Use shell as argument to CgroupManager -> DONE
#       - Restructure the code, add args to CgroupManager init (controllers, limits, etc.) -> DONE
#       - Add more cgroup controllers (memory, io, etc.)
#       - Add more cgroup functionality (put whole script under a cgroup, more granular control, etc.) -> Find a way to delete cgroup when script is done
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

    Methods:
        make_cgroup(): Create a cgroup with the specified name.
        delete_cgroup(): Delete the specified cgroup.
        add_cgroup_controller(controller): Add a cgroup controller to a specific cgroup.
        add_to_cgroup(pid): Add a process to the specified cgroup.
        set_cpu_limit(limit): Set the CPU usage limit for a specific process in the cgroup.
    """

    def __init__(self, name: str, shell, log, default_path: str = "/sys/fs/cgroup", make_cgroup=True, controllers=["cpu"], limit=0.5, limit_all=True):
        self.name = name
        self.shell = shell
        self.log = log
        self.controllers = controllers
        self.limit = limit
        self.limit_all = limit_all
        self.default_path = default_path
        self.cgroup_pth = os.path.join(self.default_path, self.name)

        if make_cgroup:
            self.make_cgroup()
        self.add_cgroup_controller()

        if self.limit_all:
            self.add_to_cgroup(os.getpid())
            self.set_cpu_limit()    

    def make_cgroup(self):
        """
        Create a cgroup with the specified name.

        Returns:
            None
        """
        if os.path.exists(self.cgroup_pth):
            self.log.info(f"\nCgroup {self.name} already exists. Skipping creation.")        
        else:
            self.shell.run(cmd=f"sudo mkdir {self.cgroup_pth}")
            self.log.info(f"\nCgroup {self.name} created.")


    def delete_cgroup(self):
        """
        Delete the specified cgroup.

        Returns:
            None
        """
        if self.limit_all:
            self.shell.run(cmd=f"truncate -s 0 {self.cgroup_pth}/cgroup.procs")

        self.shell.run(cmd=f"rmdir {self.cgroup_pth}")
        if not os.path.exists(self.cgroup_pth):
            self.log.info(f"Cgroup {self.name} deleted.")  

    def add_cgroup_controller(self):
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
        if isinstance(self.controllers, str):
            self.controllers = [self.controllers]

        for controller in self.controllers:
            self.shell.run(cmd=f"echo +'{controller}' > {self.default_path}/cgroup.subtree_control")

        # with open(f"{self.default_path}/cgroup.subtree_control", "r+") as f:
        #     for controller in controllers:
        #         if controller in f.read():
        #             print(f"\nController {controller} already exists in cgroup {self.name}. Skipping addition.")
        #         else:
        #             f.write(f"+{controller}")

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

        # with open(f"{self.default_path}/{self.name}/cgroup.procs", "r+") as f:
            # if str(pid) in f.read():
                # print(f"\nProcess {pid} already exists in cgroup {self.name}. Skipping addition.")
            # else:
                # f.write(f"{pid}")

    def set_cpu_limit(self):
        """
        Set the CPU usage limit for a specific process in the cgroup.

        Args:
            limit (int): The CPU usage limit as a percentage.

        Returns:
            None
        """
        assert 0 < self.limit <= 1, "Limit must be in range (0, 1]."

        self.shell.run(cmd=f"echo '{self.limit*100000} 100000' > {self.cgroup_pth}/cpu.max")

        # with open(f"{self.default_path}/{self.name}/cpu.max", "w") as f:
            # f.write(f'{limit*100000} 100000')  # Convert limit to a percentage



# if __name__ == "__main__":
#     shell = dummynet.HostShell(log=log, sudo=True)
#     log = logging.getLogger("dummynet")
#     log.setLevel(logging.DEBUG)

#     test = CgroupManager("test_group", shell, log=log)
#     test.add_cgroup_controller(["cpu"])
#     # test.add_to_cgroup(pid=48820)
#     # test.set_cpu_limit()
#     # test.delete_cgroup()
