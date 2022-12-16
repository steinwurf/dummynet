from dummynet import DummyNet
from dummynet import HostShell

import logging
import pathlib
import json
import sys


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

    def __init__(self, recording, shell):

        self.recording = recording
        self.shell = shell

        self.mode = None

    def open(self):

        if pathlib.Path(self.recording).is_file():
            self.mode = MockShell.Playback()
            self.mode.open(recording=self.recording)

        else:
            self.mode = MockShell.Record()
            self.mode.open(recording=self.recording, shell=self.shell)

    def close(self):
        self.mode.close()
        self.mode = None

    def run(self, cmd: str, cwd=None, detach=False):
        return self.mode.run(cmd=cmd, cwd=cwd, detach=detach)

    def run_async(self, cmd: str, daemon=False, delay=0, cwd=None):
        assert False


def test_run(datarecorder):

    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)

    # The host shell used if we don't have a recording
    host_shell = HostShell(log=log, sudo=True)

    # Create a mock shell which will receive the calls performed by the DummyNet
    shell = MockShell(recording="test/data/calls.json", shell=host_shell)

    # DummyNet wrapper that will prevent clean up from happening in playback
    # mode if an exception occurs
    

    with DummyNet(shell=shell) as dnet:

        host = dnet.host()


        # Get a list of the current namespaces
        namespaces = dnet.netns_list()
        assert namespaces == []

        # create two namespaces
        demo0 = dnet.netns_add(name="demo0")
        demo1 = dnet.netns_add(name="demo1")
        demo2 = dnet.netns_add(name="demo2")

        # Get a list of the current namespaces
        namespaces = dnet.netns_list()

        assert namespaces == ["demo2", "demo1", "demo0"]

        # Add a bridge in demo1
        demo1.bridge_add(name="br0")

        dnet.link_veth_add(p1_name="demo0-eth0", p2_name="demo1-eth0")
        dnet.link_veth_add(p1_name="demo1-eth1", p2_name="demo2-eth0")

        # Move the interfaces to the namespaces
        dnet.link_set(namespace="demo0", interface="demo0-eth0")
        dnet.link_set(namespace="demo1", interface="demo1-eth0")
        dnet.link_set(namespace="demo1", interface="demo1-eth1")
        dnet.link_set(namespace="demo2", interface="demo2-eth0")

        demo1.bridge_set(name="br0", interface="demo1-eth0")
        demo1.bridge_set(name="br0", interface="demo1-eth1")

        # Bind an IP-address to the two peers in the link.
        demo0.addr_add(ip="10.0.0.1/24", interface="demo0-eth0")
        demo2.addr_add(ip="10.0.0.2/24", interface="demo2-eth0")

        # Activate the interfaces.
        demo0.up(interface="demo0-eth0")
        demo1.up(interface="br0")
        demo1.up(interface="demo1-eth0")
        demo1.up(interface="demo1-eth1")
        demo2.up(interface="demo2-eth0")

        # We will add 20 ms of delay, 1% packet loss, a queue limit of 100 packets
        # and 10 Mbit/s of bandwidth max.
        demo1.tc(interface="demo1-eth0", delay=20, loss=1, limit=100, rate=10)
        demo1.tc(interface="demo1-eth1", delay=20, loss=1, limit=100, rate=10)

        # Show the tc-configuration of the interfaces.
        demo1.tc_show(interface="demo1-eth0")
        demo1.tc_show(interface="demo1-eth0")

        out = demo0.run(cmd="ping -c 10 10.0.0.2")

        print(out)

        # # Route the traffic through the given IPs in each of the namespaces
        # demo0.route(ip=ip1)
        # demo1.route(ip=ip2)

        # demo0.nat(ip=ip1, interface=peer1)
        # demo1.nat(ip=ip2, interface=peer2)

        # Clean up. Delete the link and the namespaces.
        # demo0.link_delete(interface=peer1)

        # demo1.bridge_add(name="br1")

        # assert(demo1.bridge_list() == ["br0", "br1"])

        # dnet.netns_delete(name=namespace1)
        # dnet.netns_delete(name=namespace2)
