from enum import Enum


class TSharkOutputFormat(Enum):
    """TShark output file format"""

    EK = "ek"
    FIELDS = "fields"
    JSON = "json"
    JSONRAW = "jsonraw"
    PDML = "pdml"
    PS = "ps"
    PSML = "psml"
    TABS = "tabs"
    TEXT = "text"


class TSharkCommand:
    def __init__(self, input_file, output_format):
        self.input_file = input_file
        self.output_format = output_format

    def cmd(self):
        return "tshark -r {} -T {}".format(self.input_file, self.output_format.value)
