import os
import dummynet

# TODO:
# DONE  - pass logger in instead of prints -> It doesn't do anything? !Explore!
# DONE  - debugger in namespace
# DONE  - Use shell as argument to CgroupManager
# DONE  - Restructure the code, add args to CgroupManager init (controllers, limits, etc.)
# DONE  - Add more cgroup controllers (memory, io, etc.) -> Make a dict like; controller: "limit_value"
# DONE  - Add more cgroup functionality (put whole script under a cgroup, more granular control, etc.) -> Find a way to delete cgroup when script is done
# DONE  - Add a way to say what to limit by how much (e.g. limit all processes in cgroup to 50% CPU, limit process 1 to 20% CPU, etc.)
# DONE  - Fix hardcoded assert in set_limit
# DONE  - Make static method that abstract building the cgroups
# DONE  - Optimize to not check 2 times if pid is list or not in cleanup and add_proc
# DONE  - Fix the cgroup cleanup by removing pid from cgroup.procs and deleting cgroup
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
        controllers (dict, optional): The cgroup controllers to add. Can be a string or a list of strings. Defaults to ["cpu"].
        pid (int, optional): The process ID to add to the cgroup. Defaults to None.

    Methods:
        make_cgroup(): Create a cgroup with the specified name.
        delete_cgroup(): Delete the specified cgroup.
        add_cgroup_controller(): Add a cgroup controller to the cgroup.
        add_to_cgroup(pid): Add a process to the specified cgroup.
        set_limit(): Set the CPU usage limit for a specific process in the cgroup.
    """

    def __init__(self, name: str,
                 shell,
                 log,
                 default_path: str = "/sys/fs/cgroup",
                 controllers: dict = {"cpu.max": None,
                                      "memory.high": None},
                 pid=None) -> None:
        
        self.name = name
        self.shell = shell
        self.log = log
        self.controllers = controllers
        self.pid = pid
        self.default_path = default_path
        self.cgroup_pth = os.path.join(self.default_path, self.name)

        # Initial clean-up
        # self.delete_cgroup()
        # self.make_cgroup()

        # self.add_cgroup_controller()
        # self.set_limit()

        # if self.pid:
        #     self.add_to_cgroup(self.pid)
    
    def build_cgroup(self):
        """
        Build cgroup by calling the following methods:
        - delete_cgroup
        - make_cgroup
        - add_cgroup_controller
        - set_limit
        - add_to_cgroup.

        Returns:
            None
        """
        self.delete_cgroup()
        self.make_cgroup()
        self.add_cgroup_controller()
        self.set_limit()
        if self.pid:
            self.add_to_cgroup(self.pid)

    def delete_cgroup(self):
        """
        Delete the specified cgroup.

        Returns:
            None
        """
        try:
            self.shell.run(cmd=f"rmdir {self.cgroup_pth}")
        except dummynet.errors.RunInfoError as e:
            self.log.info(f"Error: {e}\nContinuing...")
        else:
            self.log.info(f"Cgroup {self.name} deleted.\n")

    def make_cgroup(self):
        """
        Create a cgroup with the specified name.

        Returns:
            None
        """
        if os.path.exists(self.cgroup_pth):
            self.log.info(f"Cgroup {self.name} already exists. Skipping creation.")        
        else:
            self.shell.run(cmd=f"mkdir {self.cgroup_pth}")
            self.log.info(f"Cgroup {self.name} created.")

    def add_cgroup_controller(self):
        """
        Add a cgroup controller to the cgroup.

        Returns:
            None
        """
        for controller in self.controllers.keys():
            self.shell.run(cmd=f"echo '+{controller.split('.')[0]}' > {self.default_path}/cgroup.subtree_control")
                
    def set_limit(self):
        """
        Set the usage limit for a specific controller in the cgroup.

        Returns:
            None
        """
        # Filter out Nones
        self.controllers = {key: value for key, value in self.controllers.items() if value is not None}
        
        # Set limits for each controller
        for key, value in self.controllers.items():
            if key.startswith("cpu."):
                assert 0 < value <= 1, "Limit must be in range (0, 1]."
                self.shell.run(cmd=f"echo '{int(value*100000)} 100000' > {self.cgroup_pth}/{key}")
            elif key.startswith("memory."):
                self.shell.run(cmd=f"echo '{value}' > {self.cgroup_pth}/{key}")

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
    
        self.pid = pid
        for p in pid:
            self.shell.run(cmd=f"echo {p} > {self.cgroup_pth}/cgroup.procs")

    def cleanup(self):
        """
        Cleanup the cgroup by removing the pid from cgroup.procs and deleting the cgroup.

        Returns:
            None
        """
        for p in self.pid: 
            self.shell.run(cmd=f"echo {p} > {self.default_path}/cgroup.procs")
            self.delete_cgroup()

# if __name__ == "__main__":
#     shell = dummynet.HostShell(log=log, sudo=True)
#     log = logging.getLogger("dummynet")
#     log.setLevel(logging.DEBUG)

#     test = CgroupManager("test_group", shell, log=log)
#     test.add_cgroup_controller(["cpu"])
#     # test.add_to_cgroup(pid=48820)
#     # test.set_limit()
#     # test.delete_cgroup()
