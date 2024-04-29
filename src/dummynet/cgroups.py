import os
import dummynet
import logging


class CGroup:
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
        input_validation(): Validate the input arguments.
        build_cgroup(): Plug-and-play cgroup generator.
        make_cgroup(): Create a cgroup with the specified name.
        delete_cgroup(): Delete the specified cgroup.
        add_cgroup_controller(): Add a cgroup controller to the cgroup.
        add_to_cgroup(pid): Add a process to the specified cgroup.
        set_limit(): Set the CPU usage limit for a specific process in the cgroup.

    Example:
        >>> test_cgroup = dummynet.CgroupManager(
        name="test_cgroup",
        shell=shell,
        log=log,
        default_path="/sys/fs/cgroup",
        controllers={"cpu.max": 0.5, "memory.high": 200000000},
        pid=os.getpid(),
        )
        >>> test_cgroup_build.build_cgroup()
        >>> test_cgroup_build.cleanup()

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
    
    def build_cgroup(self):
        """
        Build cgroup by calling the following methods:
        - delete_cgroup
        - make_cgroup
        - input_validation
        - add_cgroup_controller
        - set_limit
        - add_to_cgroup.

        Returns:
            None
        """
        self.delete_cgroup()
        self.make_cgroup()
        self.input_validation()
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
            if "No such file or directory" in e.info.stderr:
                self.log.info(f"Cgroup {self.name} does not exist. Skipping deletion.\n")
            if "Device or resource busy" in e.info.stderr:
                self.log.info(f"Cgroup {self.name} failed to delete. Stop running processes before deletion.\n")
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

    def input_validation(self):
        """
        Validate the input arguments.

        Returns:
            None
        """
        assert isinstance(self.name, str), "Name must be a string."
        assert isinstance(self.shell, dummynet.HostShell), "Shell must be a dummynet.HostShell object."
        assert isinstance(self.log, logging.Logger), "Log must be a logging.Logger object."
        assert isinstance(self.default_path, str), "Default path must be a string."
        assert isinstance(self.controllers, dict), "Controllers must be a dictionary."
        assert isinstance(self.pid, (int, list, type(None))), "PID must be an integer, list or None."

    def add_cgroup_controller(self):
        """
        Add a cgroup controller to the cgroup.

        Available controllers:

        (cpuset, cpu, io, memory, hugetlb, pids, rdma, misc)

        Returns:
            None
        """
        for controller in self.controllers.keys():
            self.shell.run(cmd=f"echo '+{controller.split('.')[0]}' > {self.default_path}/cgroup.subtree_control")
        
        controller_list = os.listdir(self.cgroup_pth)
        for key in self.controllers.keys():
            assert key in controller_list, f"Controller {key} not found in cgroup directory."

    def set_limit(self):
        """
        Set the usage limit for a specific controller in the cgroup.

        Available controllers to limit:

        - cpu (percentage) -> (0, 1]
        - memory (bytes) -> (0, max]

        Returns:
            None
        """
        # Filter out Nones
        self.controllers = {key: value for key, value in self.controllers.items() if value is not None}
        
        # Set limits for each controller
        for key, value in self.controllers.items():
            if key.startswith("cpu."):
                assert 0 < value <= 1, f"{key} must be in range (0, 1]."
                self.shell.run(cmd=f"echo '{int(value*100000)} 100000' > {self.cgroup_pth}/{key}")
            elif key.startswith("memory."):
                assert value > 0, f"{key} must be greater than 0."
                self.shell.run(cmd=f"echo '{value}' > {self.cgroup_pth}/{key}")

    def add_to_cgroup(self, pid):
        """
        Add a Process to the specified cgroup via its PID.

        Args:
            pid (int): The process ID.

        Returns:
            None
        """
        if isinstance(pid, int):
            pid = [pid]
        
        # Check if pid exists
        try:
            for p in pid:
                os.kill(p, 0)
        except OSError:
            assert False, f"Process {p} is not running."
        else:
            self.pid = pid
            for p in pid:
                self.shell.run(cmd=f"echo {p} > {self.cgroup_pth}/cgroup.procs")

    def cleanup(self):
        """
        Cleanup the cgroup by removing the pid from cgroup.procs and deleting the cgroup.

        Returns:
            None
        """
        if self.pid:
            for p in self.pid: 
                self.shell.run(cmd=f"echo {p} > {self.default_path}/cgroup.procs")
            self.shell.run(cmd=f"echo 1 > {self.cgroup_pth}/cgroup.kill")
        self.delete_cgroup()
        self.log.info(f"Cleanup complete.")
