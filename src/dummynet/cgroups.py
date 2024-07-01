import os
import dummynet


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

    def __init__(
        self,
        name: str,
        shell,
        log,
        default_path: str = "/sys/fs/cgroup",
        controllers: dict = {"cpu.max": None, "memory.high": None},
        pid=None,
    ) -> None:

        self.name = name
        self.shell = shell
        self.log = log
        self.controllers = controllers
        self.pid = pid
        self.pid_list = []
        self.default_path = default_path
        self.cgroup_pth = os.path.join(self.default_path, self.name)

    @staticmethod
    def build_cgroup(cgroup, force=False):
        """
        Build cgroup by calling the following methods:

        * delete_cgroup
        * make_cgroup
        * input_validation
        * set_limit and _add_cgroup_controller
        * add_pid (if specified).

        :return: A CGroup built object.
        """
        cgroup.delete_cgroup(force)
        cgroup.make_cgroup(force)
        cgroup.input_validation()
        cgroup.set_limit(controller_dict=cgroup.controllers)
        if cgroup.pid:
            cgroup.add_pid(cgroup.pid)

        return cgroup

    def delete_cgroup(self, not_exist_ok=False):
        """
        Delete the specified cgroup.

        :param not_exist_ok: If True, ignore if cgroup does not exist, otherwise
            raise Exception if does not exist. Defaults to False.
        """
        if not not_exist_ok and not os.path.exists(self.cgroup_pth):
            raise Exception(
                f"Cgroup {self.name} already exists.\nHint: Use not_exist_ok=True to ignore if file does not exist."
            )

        try:
            self.shell.run(cmd=f"rmdir {self.cgroup_pth}")
        except dummynet.errors.RunInfoError as e:
            if "No such file or directory" in e.info.stderr:
                self.log.info(
                    f"Cgroup {self.name} does not exist. Skipping deletion.\n"
                )
            if "Device or resource busy" in e.info.stderr:
                raise Exception(
                    f"Cgroup {self.name} failed to delete. Stop running processes before deletion.\n"
                )
        else:
            self.log.info(f"Cgroup {self.name} deleted.\n")

    def make_cgroup(self, exist_ok=False):
        """
        Create a cgroup with the specified name.

        :param exist_ok: If True, force overwrite the existing cgroup, otherwise
            raise Exception if it already exists. Defaults to False.
        """
        if os.path.exists(self.cgroup_pth) and exist_ok:
            self.delete_cgroup()
        elif not exist_ok and os.path.exists(self.cgroup_pth):
            raise Exception(f"Cgroup {self.name} already exists and exist_ok=False.")

        self.shell.run(cmd=f"mkdir {self.cgroup_pth}")
        self.log.info(f"Cgroup {self.name} created.")

    def input_validation(self):
        """
        Validate the input arguments.
        """
        assert isinstance(self.name, str), "Name must be a string."
        assert isinstance(self.default_path, str), "Default path must be a string."
        assert isinstance(self.controllers, dict), "Controllers must be a dictionary."
        assert isinstance(
            self.pid, (int, list, type(None))
        ), "PID must be an integer, list or None."

    def _add_cgroup_controller(self, controller):
        """
        Add a cgroup controller to the cgroup.

        Available controllers:
        (cpuset, cpu, io, memory, hugetlb, pids, rdma, misc)

        :param controller: The controller to add.
        """

        self.shell.run(
            cmd=f" echo '+{controller.split('.')[0]}' |  tee {self.default_path}/cgroup.subtree_control"
        )

        controller_list = os.listdir(self.cgroup_pth)
        assert (
            controller in controller_list
        ), f"Controller not found in cgroup directory. Controller: {controller}"

    def set_limit(self, controller_dict: dict):
        """
        Set the usage limit for a specific controller in the cgroup.

        :param controller_dict: Dictionary of controllers as keys and limits as
            values.

        Available controllers to limit:

        * cpu (percentage) -> (0, 1]
        * memory (bytes) -> (0, max].
        """
        # Filter out Nones
        controller_dict = {
            key: value for key, value in controller_dict.items() if value is not None
        }

        # Set limits for each controller
        for key, value in controller_dict.items():
            self._add_cgroup_controller(key)
            if key.startswith("cpu."):
                assert 0 < value <= 1, f"{key} must be in range (0, 1]."
                self.shell.run(
                    cmd=f"echo '{int(value*100000)} 100000' | tee {self.cgroup_pth}/{key}"
                )
            elif key.startswith("memory."):
                assert value > 0, f"{key} must be in range [0, max]."
                self.shell.run(cmd=f"echo '{value}' | tee {self.cgroup_pth}/{key}")

    def add_pid(self, *args):
        """
        Add a Process to the specified cgroup.

        :param args: The process ID.
        """
        # Check if pid exists
        for arg in args:
            try:
                os.kill(arg, 0)
            except OSError:
                assert False, f"Process {arg} is not running."
            else:
                if arg not in self.pid_list:
                    self.pid_list.append(arg)
                self.shell.run(cmd=f"echo {arg} |  tee {self.cgroup_pth}/cgroup.procs")

    def hard_clean(self):
        """
        Cleanup the cgroup by removing the pid from cgroup.procs and deleting
        the cgroup.
        """
        if self.pid_list:
            with open(f"{self.cgroup_pth}/cgroup.procs", "r") as f:
                active_pids = f.readlines()
                active_pids = [int(p.strip("\\n")) for p in active_pids]
            for p in self.pid_list:
                if p in active_pids:
                    self.shell.run(
                        cmd=f"echo {p} | tee {self.default_path}/cgroup.procs"
                    )
            self.shell.run(cmd=f"echo 1 |  tee {self.cgroup_pth}/cgroup.kill")
        self.delete_cgroup(not_exist_ok=True)
        self.log.info(f"Cleanup complete for cgroup {self.name}.")
