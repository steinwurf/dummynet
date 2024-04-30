import os
import dummynet
import logging


class CGroup:
    """
    A class for manipulating cgroups.
    :param name: The name of the cgroup.
    :param shell: The shell object used for executing shell commands.
    :param log: The log object used for logging messages.
    :param default_path: The default path for cgroups. Defaults to "/sys/fs/cgroup".
    :param controllers: Dictionary of controllers as keys and limits as values. Defaults to {"cpu.max": None, "memory.high": None}.
    :param pid: The process ID to add to the cgroup. Defaults to None.

    Example:
        >>> test_cgroup = dummynet.CGroup(
        name="test_cgroup",
        shell=shell,
        log=log,
        default_path="/sys/fs/cgroup",
        controllers={"cpu.max": 0.5, "memory.high": 200000000},
        pid=os.getpid(),
        )
        >>> test_cgroup = dummynet.CGroup.build_cgroup(test_cgroup, force=True)
        >>> test_cgroup.hard_clean()
    """

    def __init__(self,
                 name: str,
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

    @staticmethod    
    def build_cgroup(cgroup, force=False):
        """
        Build cgroup by calling the following methods:
        - delete_cgroup
        - make_cgroup
        - input_validation
        - add_cgroup_controller
        - set_limit
        - add_pid (if specified).
        """
        print(f"{cgroup.controllers=}")
        cgroup.delete_cgroup(force)
        cgroup.make_cgroup(force)
        cgroup.input_validation()
        cgroup.set_limit(controller_dict = cgroup.controllers)
        if cgroup.pid:
            cgroup.add_pid(cgroup.pid)
    
        return cgroup

    def delete_cgroup(self, force=False):
        """
        Delete the specified cgroup.
        :param force: If True, force delete the cgroup. Defaults to False.
        """
        if not force and os.path.exists(self.cgroup_pth):
            raise Exception(f"Cgroup {self.name} already exists.\nHint: Use force=True to force delete the cgroup.")

        try:
            self.shell.run(cmd=f"rmdir {self.cgroup_pth}")
        except dummynet.errors.RunInfoError as e:
            if "No such file or directory" in e.info.stderr:
                self.log.info(f"Cgroup {self.name} does not exist. Skipping deletion.\n")
            if "Device or resource busy" in e.info.stderr:
                self.log.info(f"Cgroup {self.name} failed to delete. Stop running processes before deletion.\n")
        else:
            self.log.info(f"Cgroup {self.name} deleted.\n")

    def make_cgroup(self, force=False):
        """
        Create a cgroup with the specified name.
        :param force: If True, force overwrite the existing cgroup. Defaults to False.
        """
        if os.path.exists(self.cgroup_pth):
            raise Exception(f"Cgroup {self.name} already exists.\nHint: Use force=True to overwrite the cgroup.")
        else:
            self.shell.run(cmd=f"mkdir {self.cgroup_pth}")
            self.log.info(f"Cgroup {self.name} created.")

    def input_validation(self):
        """
        Validate the input arguments.
        """
        assert isinstance(self.name, str), "Name must be a string."
        assert isinstance(self.default_path, str), "Default path must be a string."
        assert isinstance(self.controllers, dict), "Controllers must be a dictionary."
        assert isinstance(self.pid, (int, list, type(None))), "PID must be an integer, list or None."

    def _add_cgroup_controller(self, controller):
        """
        Add a cgroup controller to the cgroup.
        Available controllers:
        (cpuset, cpu, io, memory, hugetlb, pids, rdma, misc)
        :param controller: The controller to add.
        """
        
        self.shell.run(cmd=f"echo '+{controller.split('.')[0]}' > {self.default_path}/cgroup.subtree_control")
        
        controller_list = os.listdir(self.cgroup_pth)
        assert controller in controller_list, f"Controller {controller} not found in cgroup directory."

    def set_limit(self, controller_dict: dict):
        """
        Set the usage limit for a specific controller in the cgroup.
        :param controller_dict: Dictionary of controllers as keys and limits as values.
        Available controllers to limit:
        - cpu (percentage) -> (0, 1]
        - memory (bytes) -> (0, max]
        """
        # Filter out Nones
        controller_dict = {key: value for key, value in controller_dict.items() if value is not None}
        
        # Set limits for each controller
        for key, value in controller_dict.items():
            self._add_cgroup_controller(key)
            if key.startswith("cpu."):
                assert 0 < value <= 1, f"{key} must be in range (0, 1]."
                self.shell.run(cmd=f"echo '{int(value*100000)} 100000' > {self.cgroup_pth}/{key}")
            elif key.startswith("memory."):
                assert value > 0, f"{key} must be greater than 0."
                self.shell.run(cmd=f"echo '{value}' > {self.cgroup_pth}/{key}")

    def add_pid(self, pid):
        """
        Add a Process to the specified cgroup.
        :param pid: The process ID.
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

    def hard_clean(self):
        """
        Cleanup the cgroup by removing the pid from cgroup.procs and deleting the cgroup.
        """
        if self.pid:
            for p in self.pid: 
                self.shell.run(cmd=f"echo {p} > {self.default_path}/cgroup.procs")
            self.shell.run(cmd=f"echo 1 > {self.cgroup_pth}/cgroup.kill")
        self.delete_cgroup(force=True)
        self.log.info(f"Cleanup complete for cgroup {self.name}.")
