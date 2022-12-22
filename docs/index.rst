Welcome to Dummynet's documentation!
====================================

Light weight network testing tool::

   import dummynet
   import logging

   log = logging.getLogger("dummynet")
   log.setLevel(logging.DEBUG)

   # Create a process monitor
   process_monitor = dummynet.ProcessMonitor()

   # The shell used to run commands
   shell = dummynet.HostShell(log=log, sudo=True, process_monitor=process_monitor)

   # DummyNet allows us to create a virtual network
   net = DummyNet(shell=shell)

   try:

      # Run a command on the host
      out = net.run(cmd="ping -c 5 8.8.8.8")
      out.match(stdout="5 packets transmitted*", stderr=None)

      # create two namespaces
      demo0 = net.netns_add(name="demo0")
      demo1 = net.netns_add(name="demo1")

      out = net.run_async(cmd="ping -c 5000 8.8.8.8")

      end_time = time.time() + 2

      while process_monitor.run():
         if time.time() >= end_time:
               log.debug("Test timeout")
               break

   finally:

      # Clean up.
      net.cleanup()

      # Close any running async commands
      process_monitor.stop()

.. toctree::
   :maxdepth: 2
   :hidden:

   api/api



