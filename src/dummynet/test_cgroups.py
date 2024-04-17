from unittest.mock import patch
from cgroups import CgroupManager

def test_make_cgroup():
    manager = CgroupManager("my_cgroup")
    with patch("subprocess.run") as mock_run:
        manager.make_cgroup()
        mock_run.assert_called_once_with(["sudo", "mkdir", "/sys/fs/cgroup/my_cgroup"])

def test_delete_cgroup():
    manager = CgroupManager("my_cgroup")
    with patch("subprocess.run") as mock_run:
        manager.delete_cgroup()
        mock_run.assert_called_once_with(["sudo", "rmdir", "/sys/fs/cgroup/my_cgroup"])

def test_add_cgroup_controller():
    manager = CgroupManager("my_cgroup")
    with open("/sys/fs/cgroup/cgroup.subtree_control", "w") as f:
        f.write("-")
    manager.add_cgroup_controller("cpu")
    with open("/sys/fs/cgroup/cgroup.subtree_control", "r") as f:
        assert "+cpu" in f.read()

def test_add_to_cgroup():
    manager = CgroupManager("my_cgroup")
    pid = 12345
    with open(f"/sys/fs/cgroup/my_cgroup/cgroup.procs", "w") as f:
        manager.add_to_cgroup(pid)
        f.write.assert_called_once_with(f"{pid}")

def test_set_cpu_limit():
    manager = CgroupManager("my_cgroup")
    limit = 0.5
    with open(f"/sys/fs/cgroup/my_cgroup/cpu.max", "w") as f:
        manager.set_cpu_limit(limit)
        f.write.assert_called_once_with(f'{limit*100000} 100000')