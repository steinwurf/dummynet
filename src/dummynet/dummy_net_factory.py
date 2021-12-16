import docker

from . import docker_shell
from . import host_shell
from . import dummy_net


class DummyNetFactory(object):
    def __init__(self, log):
        self.log = log

    def host(self, sudo=False):
        shell = host_shell.HostShell(log=self.log, sudo=sudo)

        return dummy_net.DummyNet(shell=shell)

    def docker(self, image_id, client=None):
        if client is None:
            client = docker.from_env()

        shell = docker_shell.DockerShell(log=self.log, client=client, image_id=image_id)

        return dummy_net.DummyNet(shell=shell)
