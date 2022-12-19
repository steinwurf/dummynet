import json
import pathlib


class MockShell:
    class Record:
        def __init__(self):
            self.name = "Record"

        def open(self, recording, shell):

            self.recording = recording
            self.shell = shell
            self.calls = []
            self.in_error = False

        def close(self):

            if self.in_error:
                # If we  have an exception, don't save the recording
                return

            with open(self.recording, "w") as f:
                json.dump(self.calls, f, indent=4)

        def run(self, cmd: str, cwd=None, detach=False):

            if self.in_error:
                # We already have an error, don't record any more calls. We
                # just pass commands to the host shell to allow cleanup to
                # happen
                return self.shell.run(cmd=cmd, cwd=cwd, detach=detach)

            # Run the command and record the output
            try:
                run = f"run(cmd={cmd}, cwd={cwd}, detach={detach})"
                out = self.shell.run(cmd=cmd, cwd=cwd, detach=detach)

            except Exception as e:
                self.in_error = True
                raise e

            self.calls.append({"run": run, "out": out})
            return out

    class Playback:
        def __init__(self):
            self.name = "Playback"

        def open(self, recording):
            with open(recording, "r") as f:
                self.calls = json.load(f)

            self.in_error = False

        def close(self):

            if not self.in_error:
                # If we didn't have an error, we should have used all the
                # calls
                assert self.calls == []

        def run(self, cmd: str, cwd=None, detach=False):

            if self.in_error:
                # We already have an error, don't check any more calls.
                return

            if len(self.calls) == 0:
                self.in_error = True
                raise Exception(f"No more calls in recording")

            call = self.calls.pop(0)
            run = f"run(cmd={cmd}, cwd={cwd}, detach={detach})"

            if run != call["run"]:
                self.in_error = True
                raise Exception(f"Expected {run} but got {call['run']}")

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

    def run(self, cmd: str, cwd=None, detach=False):
        return self.mode.run(cmd=cmd, cwd=cwd, detach=detach)

    def run_async(self, cmd: str, daemon=False, delay=0, cwd=None):
        assert False
