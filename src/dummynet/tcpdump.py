class TCPDumpCommand:
    def __init__(self, interface, filename):
        self.interface = interface
        self.filename = filename

    def cmd(self):
        return "tcpdump -i {} -w {}".format(self.interface, self.filename)
