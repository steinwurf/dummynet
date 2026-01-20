import time
from typing import Optional
import subprocess

import psutil


def wait_for_zombie(
    popen: subprocess.Popen, timeout: Optional[float] = None
) -> Optional[int]:
    """
    Waits for a subprocess.Popen or psutil.Popen object to reach zombie status.

    :raises subprocess.TimeoutExpired: If the timeout is reached before the
                                       process becomes a zombie.
    :raises psutil.AccessDenied: If the user lacks permission to poll the process.
    """
    start_time = time.monotonic()

    try:
        p = psutil.Process(popen.pid)

        while True:
            if p.status() == psutil.STATUS_ZOMBIE:
                return None
            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    raise subprocess.TimeoutExpired(
                        cmd=str(popen.args), timeout=timeout
                    )
            time.sleep(0.05)
    except psutil.NoSuchProcess:
        return popen.pid
