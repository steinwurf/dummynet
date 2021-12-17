============
Introduction
============

|PyPi| |Waf Python Tests| |Black| |Flake8| |Pip Install|

.. |PyPi| image:: https://badge.fury.io/py/dummynet.svg
    :target: https://badge.fury.io/py/dummynet

.. |Waf Python Tests| image:: https://github.com/steinwurf/dummynet-python/actions/workflows/python-waf.yml/badge.svg
   :target: https://github.com/steinwurf/dummynet-python/actions/workflows/python-waf.yml

.. |Flake8| image:: https://github.com/steinwurf/dummynet-python/actions/workflows/flake.yml/badge.svg
    :target: https://github.com/steinwurf/dummynet-python/actions/workflows/flake.yml

.. |Black| image:: https://github.com/steinwurf/dummynet-python/actions/workflows/black.yml/badge.svg
      :target: https://github.com/steinwurf/dummynet-python/actions/workflows/black.yml

.. |Pip Install| image:: https://github.com/steinwurf/dummynet-python/actions/workflows/pip.yml/badge.svg
      :target: https://github.com/steinwurf/dummynet-python/actions/workflows/pip.yml


dummynet-python is a tool for working with dummy-networks in python on Linux
machines. By dummy-networks we refer to setups with network namespaces, virtual
ethernets, etc.

The Dummynet class is a python wrapper for the linux 'ip netns' and 'ip link'
tools. The methods of the class parse args directly to the command-line in your
linux OS.

So far, Ubuntu and Debian are supported, but please make sure, that you
have the iproute2 linux-package installed with::

    apt-get install iproute2

Other Linux operating systems have not been tested, but feel free to open an
issue if support is needed.

.. contents:: Table of Contents:
   :local:

Installation
============

To install dummynet-python::

    pip install dummynet-python

Usage
=====

::

    import dummynet

    def main():

        with dummynet.host() as shell:

            demo0 = shell.netns_add(name="namespace1")
            demo1 = shell.netns_add(name="namespace2")

            shell.link_veth_add(p1_name="peer1", p2_name="peer2")

For a complete example of a local network setup see the test in
'test/test_dummynet.py'.

You can try playing around with the class methods in dummynet.py and call the
commands in self.shell.run(cmd) from the command-line. This can give a better
idea of the functionality.


Release new version
===================

1. Edit NEWS.rst and wscript (set correct VERSION)
2. Run ::

    ./waf upload

Source code
===========

The main functionality is found in ``src/dummy_net.py`` and the
corresponding unit test is in ``test/test_dummynet.py`` if you
want to play/modify/fix the code this would, in most cases, be the place
to start.

Developer Notes
===============

We try to make our projects as independent as possible of a local system setup.
For example with our native code (C/C++) we compile as much as possible from
source, since this makes us independent of what is currently installed
(libraries etc.) on a specific machine.

To "fetch" sources we use Waf (https://waf.io/) augmented with dependency
resolution capabilities: https://github.com/steinwurf/waf

The goal is to enable a work-flow where running::

    ./waf configure
    ./waf build --run_tests

Configures, builds and runs any available tests for a given project, such that
you as a developer can start hacking at the code.

For Python project this is a bit unconventional, but we think it works well.

Tests
=====

The tests will run automatically by passing ``--run_tests`` to waf::

    ./waf --run_tests

This follows what seems to be "best practice" advise, namely to install the
package in editable mode in a virtualenv.

Notes
=====

* Why use an ``src`` folder (https://hynek.me/articles/testing-packaging/).
  tl;dr you should run your tests in the same environment as your users would
  run your code. So by placing the source files in a non-importable folder you
  avoid accidentally having access to resources not added to the Python
  package your users will install...
* Python packaging guide: https://packaging.python.org/distributing/

