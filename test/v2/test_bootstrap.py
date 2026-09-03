import asyncio
import json

import pytest

from dummynet.v2.bootstrap import (
    BootstrapConfig,
    BootstrapError,
    BootstrapTimeoutError,
    LocalBootstrap,
    RunnerEndpoint,
)
from dummynet.v2.process import ProcessResult


class FakeSystemd:
    def __init__(self, states, run_result=None):
        self.states = iter(states)
        self.run_result = run_result or result()
        self.calls = []

    async def status(self, unit):
        self.calls.append(("status", unit))
        return next(self.states)

    async def run(self, unit, command):
        self.calls.append(("run", unit, command))
        return self.run_result


class FakeFile:
    def __init__(self, contents=None, appear_after=0):
        self.path = "/endpoint.json"
        self.contents = contents
        self.appear_after = appear_after
        self.exists_calls = 0

    async def exists(self, *, timeout=30):
        self.exists_calls += 1
        return self.exists_calls > self.appear_after and self.contents is not None

    async def read_text(self, *, encoding="utf-8", timeout=30):
        return self.contents

    async def write_text(self, text, *, encoding="utf-8", timeout=30):
        raise AssertionError("Bootstrap must not write the endpoint file")

    async def remove(self, *, missing_ok=False, timeout=30):
        raise AssertionError("Bootstrap must not remove the endpoint file")


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def result(returncode=0, stdout="", stderr=""):
    return ProcessResult(returncode, stdout, stderr)


def config(endpoint_file, **changes):
    values = {
        "endpoint_file": endpoint_file,
        "runner_command": ("python3", "runner.py"),
        "timeout": 1.0,
        "poll_interval": 0.1,
    }
    values.update(changes)
    return BootstrapConfig(**values)


def endpoint_file(address="127.0.0.1", port=4321, **options):
    return FakeFile(json.dumps({"address": address, "port": port}), **options)


def test_reuses_an_existing_runner():
    systemd = FakeSystemd(states=["active"])
    file = endpoint_file()

    endpoint = asyncio.run(LocalBootstrap(systemd, FakeClock()).run(config(file)))

    assert endpoint == RunnerEndpoint("127.0.0.1", 4321)
    assert systemd.calls == [("status", "dummynet-runner.service")]


def test_starts_a_missing_runner_and_waits_for_endpoint():
    systemd = FakeSystemd(states=["inactive"])
    file = endpoint_file(port=9876, appear_after=2)
    clock = FakeClock()

    endpoint = asyncio.run(LocalBootstrap(systemd, clock).run(config(file)))

    assert endpoint == RunnerEndpoint("127.0.0.1", 9876)
    assert systemd.calls == [
        ("status", "dummynet-runner.service"),
        ("run", "dummynet-runner.service", ["python3", "runner.py"]),
    ]
    assert clock.sleeps == [0.1, 0.1]


def test_losing_a_start_race_uses_the_winning_runner():
    systemd = FakeSystemd(
        states=["inactive", "activating"],
        run_result=result(returncode=1, stderr="Unit already exists"),
    )
    file = endpoint_file()

    endpoint = asyncio.run(LocalBootstrap(systemd, FakeClock()).run(config(file)))

    assert endpoint == RunnerEndpoint("127.0.0.1", 4321)
    assert [call[0] for call in systemd.calls] == ["status", "run", "status"]


def test_start_failure_is_reported():
    systemd = FakeSystemd(
        states=["inactive", "inactive"],
        run_result=result(returncode=1, stderr="permission denied"),
    )

    with pytest.raises(BootstrapError, match="permission denied"):
        asyncio.run(LocalBootstrap(systemd, FakeClock()).run(config(FakeFile())))


def test_endpoint_timeout_is_reported():
    clock = FakeClock()
    bootstrap = LocalBootstrap(FakeSystemd(states=["active"]), clock)

    with pytest.raises(BootstrapTimeoutError, match="within 1 seconds"):
        asyncio.run(bootstrap.run(config(FakeFile())))

    assert clock.now == 1.0


@pytest.mark.parametrize(
    "contents",
    [
        "not json",
        json.dumps({"address": "", "port": 1234}),
        json.dumps({"address": "runner.example.com", "port": 1234}),
        json.dumps({"address": 2130706433, "port": 1234}),
        json.dumps({"address": "127.0.0.1", "port": 0}),
        json.dumps({"address": "127.0.0.1", "port": True}),
    ],
)
def test_invalid_endpoint_is_reported(contents):
    file = FakeFile(contents)
    bootstrap = LocalBootstrap(FakeSystemd(states=["active"]), FakeClock())

    with pytest.raises(BootstrapError, match="Invalid runner"):
        asyncio.run(bootstrap.run(config(file)))


def test_ipv6_endpoint_is_supported():
    file = endpoint_file(address="2001:db8::1")
    bootstrap = LocalBootstrap(FakeSystemd(states=["active"]), FakeClock())

    endpoint = asyncio.run(bootstrap.run(config(file)))

    assert endpoint == RunnerEndpoint("2001:db8::1", 4321)
