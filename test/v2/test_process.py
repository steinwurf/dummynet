import asyncio
import os
import sys

import pytest

from dummynet.v2.process import LocalProcess, ProcessResult, SudoError


class FakeProcess(LocalProcess):
    def __init__(self, results):
        super().__init__()
        self.results = iter(results)
        self.calls = []

    async def _execute(self, command, stdin_text=None):
        self.calls.append((command, stdin_text))
        return next(self.results)


def test_process_captures_output_and_return_code():
    result = asyncio.run(
        LocalProcess().run(
            [
                sys.executable,
                "-c",
                "import sys; print('out'); print('err', file=sys.stderr); sys.exit(7)",
            ]
        )
    )

    assert result.returncode == 7
    assert result.stdout == "out\n"
    assert result.stderr == "err\n"


def test_process_does_not_invoke_a_shell():
    argument = "$(printf shell-expanded)"

    result = asyncio.run(
        LocalProcess().run(
            [sys.executable, "-c", "import sys; print(sys.argv[1])", argument]
        )
    )

    assert result.returncode == 0
    assert result.stdout == argument + "\n"


def test_process_does_not_pass_sudo_password_to_child(monkeypatch):
    monkeypatch.setenv("DUMMYNET_SUDO_PASSWD", "secret")

    result = asyncio.run(
        LocalProcess().run(
            [
                sys.executable,
                "-c",
                "import os; print(os.environ.get('DUMMYNET_SUDO_PASSWD'))",
            ]
        )
    )

    assert result.stdout == "None\n"
    assert os.environ["DUMMYNET_SUDO_PASSWD"] == "secret"


def test_process_uses_noninteractive_passwordless_sudo(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    process = FakeProcess([ProcessResult(0, "", ""), ProcessResult(0, "done", "")])

    result = asyncio.run(process.run(["command", "argument"], sudo=True))

    assert result.stdout == "done"
    assert process.calls == [
        (["sudo", "--non-interactive", "--reset-timestamp", "true"], None),
        (["sudo", "--non-interactive", "command", "argument"], None),
    ]


def test_process_supplies_sudo_password_only_on_stdin(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setenv("DUMMYNET_SUDO_PASSWD", "secret")
    process = FakeProcess(
        [
            ProcessResult(1, "", "password required"),
            ProcessResult(0, "", ""),
            ProcessResult(0, "done", ""),
        ]
    )

    result = asyncio.run(process.run(["command"], sudo=True))

    assert result.stdout == "done"
    assert process.calls == [
        (["sudo", "--non-interactive", "--reset-timestamp", "true"], None),
        (["sudo", "--reset-timestamp", "--stdin", "true"], "secret\n"),
        (["sudo", "--stdin", "command"], "secret\n"),
    ]


def test_process_rejects_invalid_sudo_password(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setenv("DUMMYNET_SUDO_PASSWD", "wrong")
    process = FakeProcess(
        [
            ProcessResult(1, "", "password required"),
            ProcessResult(1, "", "authentication failed"),
        ]
    )

    with pytest.raises(SudoError, match="Could not obtain sudo privileges"):
        asyncio.run(process.run(["command"], sudo=True))
