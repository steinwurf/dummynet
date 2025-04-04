import os
import dummynet
import enum

import psutil


class CGroup:
    """
    A class for manipulating cgroups. This class is not meant to be used
    directly, but through the ``DummyNet``-instance.

    :param name: The name of the cgroup.
    :param shell: The shell object used for executing shell commands.
    :param log: The log object used for logging messages.
    :param cpu_limit: The ratio of CPU usage limit for the cgroup. Between 0 and 1. Defaults to None.
    :param memory_limit: The memory usage hard-limit for the cgroup. In bytes. Defaults to None.
           if memory usage exceeds the limit, the processes will get killed by the kernel. OOM.

    """

    def __init__(
        self,
        name: str,
        shell,
        log,
        cpu_limit=None,
        memory_limit=None,
    ) -> None:

        assert isinstance(name, str), "Name must be a string."
        if cpu_limit is not None:
            assert 0 < cpu_limit <= 1, "CPU limit must be in range (0, 1]."

        if memory_limit is not None:
            assert (
                psutil.virtual_memory().total > memory_limit and memory_limit > 0
            ), "Memory limit must be in range [0, max]."
        self.name = name
        self.shell = shell
        self.log = log
        self.cpu_limit = cpu_limit
        self.memory_limit = memory_limit
        self.default_path = "/sys/fs/cgroup"
        self.pid_list = []
        self.cgroup_path = os.path.join(self.default_path, self.name)

        self.make_cgroup(exist_ok=False)

        for pid in self.pid_list:
            if not isinstance(pid, int):
                self.hard_clean()
                assert isinstance(pid, int), "PID must be an integer."
            if pid <= 0:
                self.hard_clean()
                assert pid > 0, "PID must be greater than 0."
            self.add_pid(pid)

    def delete_cgroup(self, not_exist_ok=False):
        """
        Delete the specified cgroup.

        :param not_exist_ok: If True, ignore if cgroup does not exist, otherwise
            raise Exception if does not exist. Defaults to False.
        """
        if not not_exist_ok and not os.path.exists(self.cgroup_path):
            raise Exception(
                f"Cgroup {self.name} already exists.\nHint: Use not_exist_ok=True to ignore if file does not exist."
            )

        try:
            self.shell.run(cmd=f"rmdir {self.cgroup_path}")
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
        if os.path.exists(self.cgroup_path) and exist_ok:
            self.delete_cgroup()
        elif not exist_ok and os.path.exists(self.cgroup_path):
            raise Exception(f"Cgroup {self.name} already exists and exist_ok=False.")

        self.shell.run(cmd=f"mkdir {self.cgroup_path}")
        self.log.info(f"Cgroup {self.name} created.")

        if self.cpu_limit:
            self.set_limit({"cpu.max": self.cpu_limit})
        if self.memory_limit:
            self.set_limit({"memory.max": self.memory_limit})

    def _add_cgroup_controller(self, controller):
        """
        Add a cgroup controller to the cgroup.

        Available controllers:
        (cpuset, cpu, io, memory, hugetlb, pids, rdma, misc)

        :param controller: The controller to add.
        """

        self.shell.run(
            cmd=f"bash -c \"echo '+{controller.split('.')[0]}' | tee {self.default_path}/cgroup.subtree_control\""
        )

        controller_list = os.listdir(self.cgroup_path)
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

        # Set limits for each controller
        for key, value in controller_dict.items():
            self._add_cgroup_controller(key)
            if key.startswith("cpu."):
                assert 0 < value <= 1, f"{key} must be in range (0, 1]."
                self.shell.run(
                    cmd=f"bash -c \"echo '{int(value*100000)} 100000' | tee {self.cgroup_path}/{key}\""
                )
            elif key.startswith("memory."):
                assert value > 0, f"{key} must be in range [0, max]."
                self.shell.run(
                    cmd=f"bash -c \"echo '{value}' | tee {self.cgroup_path}/{key}\""
                )

    def add_pid(self, pid):
        """
        Add a Process to the specified cgroup.

        :param args: The process ID.
        """
        # Check if pid exists

        assert isinstance(pid, int), "PID must be an integer."
        assert pid > 0, "PID must be greater than 0."

        try:
            os.kill(pid, 0)
        except OSError as e:
            # Clean up the cgroup if pid does not exist, so it doesnt persist past errors.
            self.hard_clean()
            raise e

        if pid not in self.pid_list:
            self.pid_list.append(pid)
        self.shell.run(
            cmd=f'bash -c "echo {pid} |  tee {self.cgroup_path}/cgroup.procs"'
        )

    def hard_clean(self):
        """
        Cleanup the cgroup by removing the pid from cgroup.procs and deleting
        the cgroup.
        """
        if self.pid_list:
            with open(f"{self.cgroup_path}/cgroup.procs", "r") as f:
                active_pids = f.readlines()
                active_pids = [int(p.strip("\\n")) for p in active_pids]
            for p in self.pid_list:
                if p in active_pids:
                    self.shell.run(
                        cmd=f'bash -c "echo {p} | tee {self.default_path}/cgroup.procs"'
                    )
            self.shell.run(cmd=f'bash -c "echo 1 | tee {self.cgroup_path}/cgroup.kill"')
        self.delete_cgroup(not_exist_ok=True)
        self.log.info(f"Cleanup complete for cgroup {self.name}.")
