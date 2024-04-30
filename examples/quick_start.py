import dummynet
import logging
import sys
import argparse


def run():

    parser = argparse.ArgumentParser(description="Program with debugger option")
    parser.add_argument("--debug", action="store_true", help="Enable log debugger")
    args = parser.parse_args()

    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)
    
    if args.debug:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        log.addHandler(console_handler)

    process_monitor = dummynet.ProcessMonitor(log=log)
    shell = dummynet.HostShell(log=log, sudo=True, process_monitor=process_monitor)
    net = dummynet.DummyNet(shell=shell)

    cgroup0 = net.add_cgroup(name="test_cgroup0",
                            shell=shell,
                            log = log,
                            controllers={"cpu.max": 0.5, "memory.high": 200000000},
                            pid=None)
    cgroup1 = net.add_cgroup(name="test_cgroup1",
                            shell=shell,
                            log = log,
                            controllers={"cpu.max": 0.2, "memory.high": 100000000})

    cgroup0 = dummynet.CGroup.build_cgroup(cgroup0, force=True)

    cgroup1.delete_cgroup(force=True)
    cgroup1.make_cgroup()
    cgroup1.input_validation()
    cgroup1.set_limit(cgroup1.controllers)
    
    try:

        # Get a list of the current namespaces
        namespaces = net.netns_list()
        assert namespaces == []

        # create two namespaces
        demo0 = net.netns_add(name="demo0")
        demo1 = net.netns_add(name="demo1")

        net.link_veth_add(p1_name="demo0-eth0", p2_name="demo1-eth0")

        # Move the interfaces to the namespaces
        net.link_set(namespace="demo0", interface="demo0-eth0")
        net.link_set(namespace="demo1", interface="demo1-eth0")

        # Bind an IP-address to the two peers in the link.
        demo0.addr_add(ip="10.0.0.1/24", interface="demo0-eth0")
        demo1.addr_add(ip="10.0.0.2/24", interface="demo1-eth0")

        # Activate the interfaces.
        demo0.up(interface="demo0-eth0")
        demo1.up(interface="demo1-eth0")
        demo0.up(interface="lo")
        demo1.up(interface="lo")

        # Test will run until last non-daemon process is done.
        proc0 = demo0.run_async(cmd="ping -c 20 10.0.0.2", daemon=True)
        proc1 = demo1.run_async(cmd="ping -c 10 10.0.0.1")
        
        # # Add the processes to the cgroup.
        cgroup0.add_pid(pid=proc0.pid)
        cgroup1.add_pid(pid=proc1.pid)

        # Print output as we go (optional)
        def _proc0_stdout(data):
            print("proc0: {}".format(data))

        def _proc1_stdout(data):
            print("proc1: {}".format(data))

        proc0.stdout_callback = _proc0_stdout
        proc1.stdout_callback = _proc1_stdout

        while process_monitor.run():
            pass

        # Check that the ping succeeded.
        proc1.match(stdout="10 packets transmitted*", stderr=None)

        # Since proc0 is a daemon we automatically kill it when the last
        # non-daemon process is done. However we can still see the output it
        # generated.
        print(f"proc0: {proc0.stdout}")

    finally:

        # Clean up.
        net.cleanup()
        net.cgroup_cleanup()


if __name__ == "__main__":
    run()
