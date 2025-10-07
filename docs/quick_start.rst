Quick Start
===========

This guide will help you get up and running with Dummynet quickly. Dummynet is
a Python library for creating network emulation environments, allowing you to
simulate various network conditions for testing purposes.

Installation
------------

The fastest way to get started is to install Dummynet using pip:

.. code-block:: bash

   python3 -m pip install dummynet

Prerequisites
~~~~~~~~~~~~~

Dummynet requires:

* Python 3.11 or higher
* Linux operating system (tested on Ubuntu 20.04+)
* Root privileges or appropriate capabilities for network namespace manipulation
* ``iproute2`` and ``iptables`` packages installed

Basic Usage
-----------

DummyNet depends upon the creation of a root host shell to run its commands. To create it,
you can use the following pattern:

.. code-block:: python

    import dummynet
    import logging
    import os

    # Check if we need to run as sudo
    sudo = os.getuid() != 0

    # Create a process monitor
    log = logging.getLogger("dummynet")
    log.setLevel(logging.DEBUG)
    process_monitor = dummynet.ProcessMonitor(log=log)

    # Create the host shell
    shell = dummynet.HostShell(log=log, sudo=sudo, process_monitor=process_monitor)

Context Manager (Recommended)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The recommended way to use Dummynet is with a context manager, which ensures
cleanup steps always run on exit:

.. code-block:: python

   with dummynet.DummyNet(shell=shell) as net:
       # Your network code here, e.g.
       net.link_veth_pair("veth0", "veth1")
   # Cleanup happens automatically

Manual Management
~~~~~~~~~~~~~~~~~

For more control, you can manage the lifecycle manually:

.. code-block:: python

   net = dummynet.DummyNet(shell=shell)
   try:
       # Your network code here, e.g.
       net.link_veth_pair("veth0", "veth1")
   finally:
       net.cleanup()

.. warning::
   Always ensure ``net.cleanup()`` is called when using manual management to avoid
   leaving any network artifacts dangling on your system!

Interface Management
--------------------

Dummynet uses a special naming convention for interfaces to support concurrent
execution:

.. code-block:: python

   # Create a veth pair using dummynet
   net.link_veth_pair("veth0", "veth1")

This creates a veth pair locally called ``d-XXXX-veth0`` and ``d-XXXX-veth1``,
where:

* ``d-`` is the Dummynet prefix
* ``XXXX`` is the current Python process ID encoded as a base58 string
* ``veth0`` is your specified interface name

This naming scheme allows multiple Dummynet instances to run concurrently inside
multiple Python instances without conflicts, making it particularly useful for
parallelized testing with tools like ``pytest-xdist``.

When using strings, these will always point to these scoped variants.

.. code-block:: python

    example_netns = net.netns_add("example")
    net.link_set("eth0", namespace=example_netns)
    # This will fail! As it actually points to `d-XXXX-eth0`,
    # which doesn't exist!

    # The correct actions would be to first create the scoped interfaces
    net.link_veth_pair("eth0", "eth1")
    net.link_set("eth0", namespace=example_netns)
    # this will now move `d-XXXX-eth0` without error.

It is therefore reccomended to use the scoped variables returned by
dummynet to explicitly show this behaviour, instead of relying on the
string-based API.

.. code-block:: python

    example_netns = net.netns_add("example")
    veth0, veth1 = net.link_veth_pair("veth0", "veth1")
    net.link_set(veth0, namespace=example_netns)

To actually point at system devices, some are listed as ``UNSCOPED_NAMES``, like
the loopback interface ``lo``, which will never be scoped. If you still need a
system interface, you can use the ``InterfaceScoped`` class directly, and set its
``uid`` to 0, which acts as a magic variable to always keep the interface
unscoped.

.. code-block:: python

    example_netns = net.netns_add("example")
    eth0 = dummynet.InterfaceScoped("eth0", uid=0)
    net.link_set(eth0, namespace=example_netns)
    # This will actually move `eth0`, be careful!


Complete Example
----------------

Here's a complete example demonstrating DummyNet:

.. literalinclude:: ../examples/quick_start.py
    :language: python
    :linenos:
