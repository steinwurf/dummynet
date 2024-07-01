#! /usr/bin/env python
# encoding: utf-8

from waflib.Build import BuildContext
from waflib import Logs
import waflib

import os

top = "."

VERSION = "2.6.0"


class UploadContext(BuildContext):
    cmd = "upload"
    fun = "upload"


def options(opt):

    gr = opt.get_option_group("Build and installation options")

    gr.add_option(
        "--run_tests", default=False, action="store_true", help="Run all unit tests"
    )

    gr.add_option(
        "--pytest_basetemp",
        default="pytest_temp",
        help="Set the basetemp folder where pytest executes the tests",
    )

    gr.add_option(
        "--development",
        default=False,
        action="store_true",
        help="Does not remove the virtualenv and installs the python package as an editable package",
    )


def build(bld):

    # Create a virtualenv in the source folder and build universal wheel
    with bld.create_virtualenv() as venv:

        venv.run(cmd="python -m pip install wheel")
        venv.run(cmd="python setup.py bdist_wheel --universal", cwd=bld.path)

    # Run the unit-tests
    if bld.options.run_tests:
        _pytest(bld=bld)

    # Delete the egg-info directory, do not understand why this is created
    # when we build a wheel. But, it is - perhaps in the future there will
    # be some way to disable its creation.
    egg_info = os.path.abspath(os.path.join("src", "dummynet.egg-info"))

    if os.path.isdir(egg_info):
        waflib.extras.wurf.directory.remove_directory(path=egg_info)


def _find_wheel(ctx):
    """Find the .whl file in the dist folder."""

    wheel = ctx.path.ant_glob("dist/*-" + VERSION + "-*.whl")

    if not len(wheel) == 1:
        ctx.fatal("No wheel found (or version mismatch)")
    else:
        wheel = wheel[0]
        Logs.info("Wheel %s", wheel)
        return wheel


def upload(bld):
    """Upload the built wheel to PyPI (the Python Package Index)"""

    with bld.create_virtualenv() as venv:
        venv.run("python -m pip install twine")

        wheel = _find_wheel(ctx=bld)

        venv.run(f"python -m twine upload {wheel}")


def prepare_release(ctx):
    """Prepare a release."""

    with ctx.rewrite_file(filename="setup.py") as f:
        pattern = r'VERSION = "\d+\.\d+\.\d+"'
        replacement = f'VERSION = "{VERSION}"'

        f.regex_replace(pattern=pattern, replacement=replacement)


def docs(ctx):
    """Build the documentation"""

    ctx.pip_compile(
        requirements_in="docs/requirements.in", requirements_txt="docs/requirements.txt"
    )

    with ctx.create_virtualenv() as venv:
        venv.run("python -m pip install -r docs/requirements.txt")

        build_path = os.path.join(ctx.path.abspath(), "build", "docs")

        venv.run("giit clean . --build_path {}".format(build_path))
        venv.run("giit sphinx . --build_path {}".format(build_path))


def _pytest(bld):

    # Ensure that the requirements.txt is up to date
    bld.pip_compile(
        requirements_in="test/requirements.in", requirements_txt="test/requirements.txt"
    )

    # If in development mode we do not remove the virtualenv
    if bld.options.development:
        _pytest_dev(bld=bld)

    else:
        _pytest_run(bld=bld)


def _pytest_dev(bld):
    venv = bld.create_virtualenv(name="test-venv")
    venv.run("python -m pip install -r test/requirements.txt")
    venv.run("python -m pip install -e .")


def _pytest_run(bld):

    venv = bld.create_virtualenv(overwrite=True)
    venv.run("python -m pip install -r test/requirements.txt")

    # Install the dummynet plugin in the virtualenv
    wheel = _find_wheel(ctx=bld)

    venv.run(f"python -m pip install {wheel}")

    # Added our systems path to the virtualenv
    venv.env["PATH"] = os.path.pathsep.join([venv.env["PATH"], os.environ["PATH"]])

    # We override the pytest temp folder with the basetemp option,
    # so the test folders will be available at the specified location
    # on all platforms. The default location is the "pytest" local folder.
    basetemp = os.path.abspath(os.path.expanduser(bld.options.pytest_basetemp))

    # We need to manually remove the previously created basetemp folder,
    # because pytest uses os.listdir in the removal process, and that fails
    # if there are any broken symlinks in that folder.
    if os.path.exists(basetemp):
        waflib.extras.wurf.directory.remove_directory(path=basetemp)

    # Run all tests by just passing the test directory. Specific tests can
    # be enabled by specifying the full path e.g.:
    #
    #     'test/test_run.py::test_create_context'
    #
    test_filter = "test"

    # Main test command
    venv.run(f"python -B -m pytest {test_filter} --basetemp {basetemp}")

    # Check the package
    venv.run(f"twine check {wheel}")
