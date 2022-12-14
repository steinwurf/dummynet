from dummynet import DummyNet
from dummynet import HostShell

import logging
import pathlib
import json
import sys

peer1 = "demo0-eth"
peer2 = "demo1-eth"

namespace1 = "demo0"
namespace2 = "demo1"

ip1 = "10.0.0.1"
ip2 = "10.0.0.2"

subnet = "24"


class MockShell:

    class Record:

        def open(self, recording, shell):

            self.recording = recording
            self.shell = shell
            self.calls = []

        def close(self):
            with open(self.recording, "w") as f:
                json.dump(self.calls, f, indent=4)


        def run(self, cmd: str, cwd=None, detach=False):
            run = f"run(cmd={cmd}, cwd={cwd}, detach={detach})"
            out = self.shell.run(cmd=cmd, cwd=cwd, detach=detach)
            self.calls.append({"run": run, "out": out})
            return out


    class Playback:

        def open(self, recording):
            with open(recording, "r") as f:
                self.calls = json.load(f)

        def close(self):

            if sys.exc_info()[0] is None:
                # If we already have an exception, don't raise another one
                assert(self.calls == [])

        def run(self, cmd: str, cwd=None, detach=False):
            call = self.calls.pop(0)
            run = f"run(cmd={cmd}, cwd={cwd}, detach={detach})"

            if run != call["run"]:
                raise Exception(f"Expected {run} but got {call['run']}")

            return call["out"]

    def __init__(self, recording, shell):

        self.recording = recording
        self.shell = shell

        self.mode = None

    def open(self):

        if  pathlib.Path(self.recording).is_file():
            self.mode = MockShell.Playback()
            self.mode.open(recording=self.recording)

        else:
            self.mode = MockShell.Record()
            self.mode.open(recording=self.recording, shell=self.shell)

    def close(self):
        self.mode.close()


    def run(self, cmd: str, cwd=None, detach=False):
        return self.mode.run(cmd=cmd, cwd=cwd, detach=detach)


    def run_async(self, cmd: str, daemon=False, delay=0, cwd=None):
        assert False


def test_run(datarecorder):

    log = logging.getLogger("dummynet")

    # The host shell used if we don't have a recording
    host_shell = HostShell(log=log, sudo=True)

    # Create a mock shell which will receive the calls performed by the DummyNet
    shell = MockShell(recording="test/data/calls.json", shell=host_shell)

    with DummyNet(shell=shell) as dnet:

        # Get a list of the current namespaces
        namespaces = dnet.netns_list()
        assert namespaces == []

        # create two namespaces
        demo0 = dnet.netns_add(name=namespace1)
        demo1 = dnet.netns_add(name=namespace2)

        # Get a list of the current namespaces
        namespaces = dnet.netns_list()

        assert namespace1 in namespaces
        assert namespace2 in namespaces

        # Add a link. This will go between the namespaces.
        dnet.link_veth_add(p1_name=peer1, p2_name=peer2)

        dnet.link_set(namespace=namespace1, interface=peer1)
        dnet.link_set(namespace=namespace2, interface=peer2)

        # Bind an IP-address to the two peers in the link.
        demo0.addr_add(ip=ip1 + "/" + subnet, interface=peer1)
        demo1.addr_add(ip=ip2 + "/" + subnet, interface=peer2)

        # Activate the interfaces.
        demo0.up(interface=peer1)
        demo1.up(interface=peer2)

        # We will add 20 ms of delay, 1% packet loss, a queue limit of 100 packets
        # and 10 Mbit/s of bandwidth max.
        demo0.tc(interface=peer1, delay=20, loss=1, limit=100, rate=10)
        demo1.tc(interface=peer2, delay=20, loss=1, limit=100, rate=10)

        # Show the tc-configuration of the interfaces.
        demo0.tc_show(interface=peer1)
        demo1.tc_show(interface=peer2)

        # Route the traffic through the given IPs in each of the namespaces
        demo0.route(ip=ip1)
        demo1.route(ip=ip2)

        demo0.nat(ip=ip1, interface=peer1)
        demo1.nat(ip=ip2, interface=peer2)

        # Clean up. Delete the link and the namespaces.
        demo0.link_delete(interface=peer1)

        demo1.bridge_add(name="br0")
        demo1.bridge_add(name="br1")

        assert(demo1.bridge_list() == ["br0", "br1"])

        dnet.netns_delete(name=namespace1)
        dnet.netns_delete(name=namespace2)


