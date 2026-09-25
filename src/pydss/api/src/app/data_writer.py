from pydss.api.src.app.hdf5 import Hdf5Writer
from pydss.api.src.app.json_writer import JsonWriter


class DataWriter:
    modes = {
        "h5": Hdf5Writer,
        "json": JsonWriter,
        # 'parquet': parquetWriter,
        # "pickle": pickleWriter,
    }

    def __init__(self, log_dir, format, column_length):
        self.writer = self.modes[format](log_dir, column_length)

    def write(self, fed_name, currenttime, powerflow_output, index):
        self.writer.write(fed_name, currenttime, powerflow_output, index)
