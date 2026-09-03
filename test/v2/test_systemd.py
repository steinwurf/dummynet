import asyncio

from dummynet.v2.process import ProcessResult
from dummynet.v2.systemd import LocalSystemd


class FakeProcess:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    async def run(self, command, sudo=False):
        self.calls.append((command, sudo))
        return next(self.results)


def test_status_returns_systemd_active_state():
    process = FakeProcess([ProcessResult(0, "active\n", "")])

    state = asyncio.run(LocalSystemd(process).status("dummynet-runner.service"))

    assert state == "active"
    assert process.calls == [
        (
            [
                "systemctl",
                "show",
                "--property=ActiveState",
                "--value",
                "dummynet-runner.service",
            ],
            True,
        )
    ]


def test_run_starts_a_collected_transient_service():
    expected = ProcessResult(0, "", "")
    process = FakeProcess([expected])

    result = asyncio.run(
        LocalSystemd(process).run("dummynet-runner.service", ["python3", "runner.py"])
    )

    assert result is expected
    assert process.calls == [
        (
            [
                "systemd-run",
                "--unit=dummynet-runner.service",
                "--collect",
                "--service-type=exec",
                "--property=Restart=no",
                "python3",
                "runner.py",
            ],
            True,
        )
    ]
