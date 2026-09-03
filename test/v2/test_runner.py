import asyncio
import json
import subprocess
import sys
import time

import pytest

from dummynet.v2.runner import RunnerConfig, RunnerContext, run_runner


class FakeNetwork:
    def __init__(self, events):
        self.events = events

    async def listen(self, address, port):
        self.events.append(("listen", address, port))
        return {"address": address, "port": 4321}

    async def close(self):
        self.events.append(("close",))


class FakeFile:
    path = "/endpoint.json"

    def __init__(self, events, write_error=None):
        self.events = events
        self.write_error = write_error

    async def exists(self, *, timeout=30):
        raise AssertionError("Runner must not inspect the endpoint file")

    async def read_text(self, *, encoding="utf-8", timeout=30):
        raise AssertionError("Runner must not read the endpoint file")

    async def write_text(self, text, *, encoding="utf-8", timeout=30):
        self.events.append(("write", text))
        if self.write_error:
            raise self.write_error

    async def remove(self, *, missing_ok=False, timeout=30):
        self.events.append(("remove", missing_ok))


class ImmediateClock:
    def __init__(self, events):
        self.events = events

    async def sleep(self, seconds):
        self.events.append(("sleep", seconds))


class BlockingClock:
    def __init__(self, events):
        self.events = events
        self.started = asyncio.Event()

    async def sleep(self, seconds):
        self.events.append(("sleep", seconds))
        self.started.set()
        await asyncio.Event().wait()


def context(events, clock=None, write_error=None):
    return RunnerContext(
        config=config(),
        endpoint_file=FakeFile(events, write_error),
        network=FakeNetwork(events),
        clock=clock or ImmediateClock(events),
    )


def config():
    return RunnerConfig(idle_timeout=12.0)


def test_runner_publishes_endpoint_and_cleans_up_after_idle_timeout():
    events = []

    asyncio.run(run_runner(context(events)))

    assert events == [
        ("listen", "127.0.0.1", 0),
        ("write", '{"address": "127.0.0.1", "port": 4321}'),
        ("sleep", 12.0),
        ("close",),
        ("remove", True),
    ]


def test_runner_cleans_up_when_cancelled():
    async def scenario():
        events = []
        clock = BlockingClock(events)
        task = asyncio.create_task(run_runner(context(events, clock)))
        await clock.started.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        return events

    events = asyncio.run(scenario())

    assert events[-2:] == [("close",), ("remove", True)]


def test_runner_closes_listener_when_endpoint_publication_fails():
    events = []

    with pytest.raises(OSError, match="disk full"):
        asyncio.run(run_runner(context(events, write_error=OSError("disk full"))))

    assert events[-1] == ("close",)
    assert not any(event[0] == "remove" for event in events)


def test_runner_module_publishes_and_removes_real_endpoint(tmp_path):
    endpoint_path = tmp_path / "endpoint.json"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "dummynet.v2.runner",
            "--endpoint-path",
            str(endpoint_path),
            "--idle-timeout",
            "0.5",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        deadline = time.monotonic() + 2.0
        while not endpoint_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)

        assert endpoint_path.exists()
        endpoint = json.loads(endpoint_path.read_text(encoding="utf-8"))
        assert endpoint["address"] == "127.0.0.1"
        assert 1 <= endpoint["port"] <= 65535

        stdout, stderr = process.communicate(timeout=2.0)
        assert process.returncode == 0, (stdout, stderr)
        assert not endpoint_path.exists()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=2.0)
