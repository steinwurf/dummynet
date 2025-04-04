import os
import io
import re
import sys

from setuptools import setup, find_packages

cwd = os.path.abspath(os.path.dirname(__file__))

with io.open(os.path.join(cwd, "README.rst"), encoding="utf-8") as fd:
    long_description = fd.read()

VERSION = "5.0.0"

setup(
    name="dummynet",
    version=VERSION,
    description=("A tool for creating dummy networks using network namespaces."),
    long_description=long_description,
    long_description_content_type="text/x-rst",
    url="https://github.com/steinwurf/dummynet",
    author="Steinwurf ApS",
    author_email="contact@steinwurf.com",
    license='BSD 3-clause "New" or "Revised" License',
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Plugins",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development",
        "Topic :: Software Development :: Testing",
    ],
    keywords=["dummynet", "network", "namespace"],
    packages=find_packages(where="src", exclude=["test"]),
    package_dir={"": "src"},
    install_requires=[
        "psutil==7.0.0",
    ],
)
