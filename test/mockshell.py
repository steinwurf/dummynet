import json
import pathlib


class MockShellError(Exception):
    pass


class MockShell:
    class Record:
        def __init__(self):
            self.name = "Record"

        def open(self, recording, shell):

            self.recording = recording
            self.shell = shell
            self.calls = []

        def close(self):
            """Write the calls to the recording file"""

            with open(self.recording, "w") as f:
                json.dump(self.calls, f, indent=4)

        def run(self, cmd: str, cwd=None, detach=False):

            # Run the command and record the output
            run = f"run(cmd={cmd}, cwd={cwd}, detach={detach})"
            out = self.shell.run(cmd=cmd, cwd=cwd, detach=detach)

            self.calls.append({"run": run, "out": out})
            return out

    class Playback:
        def __init__(self):
            self.name = "Playback"

        def open(self, recording):
            with open(recording, "r") as f:
                self.calls = json.load(f)

        def close(self):

            if self.calls != []:
                raise MockShellError(f"Unused calls: {self.calls}")

        def run(self, cmd: str, cwd=None, detach=False):

            if len(self.calls) == 0:
                raise MockShellError(f"No more calls in recording")

            call = self.calls.pop(0)
            run = f"run(cmd={cmd}, cwd={cwd}, detach={detach})"

            if run != call["run"]:
                raise MockShellError(f"Expected {run} but got {call['run']}")

            return call["out"]

    def __init__(self):
        self.mode = None

    def open(self, recording, shell):

        if pathlib.Path(recording).is_file():
            self.mode = MockShell.Playback()
            self.mode.open(recording=recording)

        else:
            self.mode = MockShell.Record()
            self.mode.open(recording=recording, shell=shell)

    def close(self):
        self.mode.close()
        self.mode = None

    def run(self, cmd, cwd=None):
        return self.mode.run(cmd=cmd, cwd=cwd)

    def run_async(self, cmd, daemon=False, cwd=None):
        assert False, "Mock shell doesn't support async commands"
