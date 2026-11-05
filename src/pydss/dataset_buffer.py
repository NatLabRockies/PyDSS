"""Contains DatasetBuffer"""

from loguru import logger
import pandas as pd
import numpy as np

from pydss.exceptions import InvalidConfiguration
from pydss.utils.utils import make_timestamps
from pydss.common import DatasetPropertyType



KiB = 1024
MiB = KiB * KiB
GiB = MiB * MiB

# The optimal number of chunks to store in memory will vary widely.
# The h5py docs recommend keeping chunk byte sizes between 10 KiB - 1 MiB.
# It needs to be larger than the biggest possible row and also cover enough
# columns to compress duplicate values. Since we might store thousands of
# elements in one dataset, make it the max by default.
# Note that the downside to making this larger is that any read causes the
# entire chunk to be read.
DEFAULT_MAX_CHUNK_BYTES = 1 * MiB

class DatasetBuffer:
    """Provides a write buffer to an HDF dataset to increase performance.
    Users must call flush_data before the object goes out of scope to ensure
    that all data is flushed.

    """
    # TODO add support for context manager, though pydss wouldn't be able to
    # take advantage in its current implementation.

    def __init__(
            self, hdf_store, path, max_size, dtype, columns, scaleoffset=None,
            max_chunk_bytes=None, attributes=None, names=None,
            column_ranges_per_name=None, data=None
        ):

        if max_chunk_bytes is None:
            max_chunk_bytes = DEFAULT_MAX_CHUNK_BYTES
        self._buf_index = 0
        self._hdf_store = hdf_store
        self._max_size = max_size
        num_columns = len(columns)
        if data is None:
            self.chunk_count = self.compute_chunk_count(
                num_columns,
                max_size,
                dtype,
                max_chunk_bytes,
            )
            shape = (self._max_size, num_columns)
            chunks = (self.chunk_count, num_columns)
        else:
            self.chunk_count = None
            shape = None
            chunks = None

        dim = len(shape)
        print(path)
        self._dataset = self._hdf_store.create_dataset(
            name=path,
            shape=shape,
            data=data,
            chunks=chunks,
            dtype=dtype,
            compression="gzip",
            compression_opts=4,
            shuffle=True,
            maxshape=[None for _ in range(dim)],
            # Does not preserve NaN, so don't use it.
            #scaleoffset=scaleoffset,
        )

        # Columns, names, and column_ranges_per_name can't be stored as
        # attributes because they can exceed the size limit. Store as datasets
        # instead.
        column_dataset_path = path + "Columns"
        column_dataset = self._hdf_store.create_dataset(
            name=column_dataset_path,
            data=np.array(columns, dtype="S"),
            maxshape=(None, ),
        )
        column_dataset.attrs["type"] = DatasetPropertyType.METADATA.value
        self._dataset.attrs["column_dataset_path"] = column_dataset_path

        if names is not None:
            name_dataset_path = path + "Names"
            name_dataset = self._hdf_store.create_dataset(
                name = name_dataset_path,
                data = np.array(names, dtype="S"),
                maxshape=(None, ),
            )
            name_dataset.attrs["type"] = DatasetPropertyType.METADATA.value
            self._dataset.attrs["name_dataset_path"] = name_dataset_path

        if column_ranges_per_name is not None:
            column_ranges_dataset_path = path + "ColumnRanges"
            data = np.array(column_ranges_per_name)
            dim = len(data.shape)
            column_ranges_dataset = self._hdf_store.create_dataset(
                name=column_ranges_dataset_path,
                data=data,
                maxshape=[None for _ in range(dim)],
            )
            column_ranges_dataset.attrs["type"] = DatasetPropertyType.METADATA.value
            self._dataset.attrs["column_ranges_dataset_path"] = column_ranges_dataset_path

        self._dataset.attrs["length"] = 0
        self._dataset_index = 0
        self._buf = np.empty(chunks, dtype=dtype)

        if attributes is not None:
            for attr, val in attributes.items():
                self._dataset.attrs[attr] = val

        logger.debug("Created DatasetBuffer path=%s shape=%s chunks=%s",
                     path, shape, chunks)

    def __del__(self):
        assert self._buf_index == 0, \
            f"DatasetBuffer destructed with data in memory: {self._dataset.name}"

    def flush_data(self):
        """Flush the data in the temporary buffer to storage."""
        length = self._buf_index
        if length == 0:
            return

        new_index = self._dataset_index + length
        
        if new_index > self._dataset.shape[0]:
            new_dimensions = (new_index, self._dataset.shape[1])
            self._dataset.resize(new_dimensions)
            logger.warning(f"result index {new_index} exceed dataset dimension {self._dataset.shape[0]} for dataset {self._dataset.name}. Resizig dataset to {new_dimensions}")
  
        self._dataset[self._dataset_index:new_index] = self._buf[0:length]
        
        self._buf_index = 0
        self._dataset_index = new_index
        self._dataset.attrs["length"] = new_index
        self._dataset.flush()

    def max_num_bytes(self):
        """Return the maximum number of bytes the container could hold.

        Returns
        -------
        int

        """
        size_row = self._buf.size * self._buf.itemsize / len(self._buf)
        return size_row * self._max_size

    def write_value(self, value):
        """Write the value to the internal buffer, flushing when full."""

        self._buf[self._buf_index] = value
        self._buf_index += 1
        if self._buf_index == self.chunk_count:
            self.flush_data()

    def write_data(self, values):
        """Write the data to the dataset."""
        new_index = self._dataset_index + len(values)
        self._dataset[self._dataset_index:new_index] = values
        self._dataset_index = new_index
        self._dataset.attrs["length"] = new_index

    @staticmethod
    def compute_chunk_count(
            num_columns,
            max_size,
            dtype,
            max_chunk_bytes=DEFAULT_MAX_CHUNK_BYTES
        ):
        assert max_size > 0, f"max_size={max_size}"
        tmp = np.empty((1, num_columns), dtype=dtype)
        size_row = tmp.size * tmp.itemsize
        chunk_count = min(int(max_chunk_bytes / size_row), max_size)
        if chunk_count == 0:
            raise InvalidConfiguration(
                f"HDF Max Chunk Bytes is smaller than the size of a row. Please increase it. " \
                f"max_chunk_bytes={max_chunk_bytes} num_columns={num_columns} " \
                f"size_row={size_row}"
            )

        return chunk_count

    @staticmethod
    def get_column_ranges(dataset):
        """Return the column ranges per name for the dataset.

        Parameters
        ----------
        dataset : h5py.Dataset

        Returns
        -------
        list

        """
        column_ranges_dataset = dataset.file[dataset.attrs["column_ranges_dataset_path"]]
        return column_ranges_dataset[:]

    @staticmethod
    def get_columns(dataset):
        """Return the columns for the dataset.

        Parameters
        ----------
        dataset : h5py.Dataset

        Returns
        -------
        list

        """
        col_dataset = dataset.file[dataset.attrs["column_dataset_path"]]
        return [x.decode("utf8") for x in col_dataset[:]]

    @staticmethod
    def get_names(dataset):
        """Return the names for the dataset.

        Parameters
        ----------
        dataset : h5py.Dataset

        Returns
        -------
        list

        """
        name_dataset = dataset.file[dataset.attrs["name_dataset_path"]]
        return [x.decode("utf8") for x in name_dataset[:]]

    @staticmethod
    def to_dataframe(dataset, column_range=None):
        """Create a pandas DataFrame from a dataset created with this class.

        Parameters
        ----------
        dataset : h5py.Dataset
        column_range : None | list
            first element is column start, second element is length

        Returns
        -------
        pd.DataFrame

        """
        length = dataset.attrs["length"]
        columns = DatasetBuffer.get_columns(dataset)
        if column_range is None:
            return pd.DataFrame(dataset[:length], columns=columns)

        start = column_range[0]
        end = start + column_range[1]
        return pd.DataFrame(
            dataset[:length, start:end],
            columns=columns[start:end],
        )

    @staticmethod
    def to_datetime(dataset):
        """Create a pandas DatetimeIndex from a dataset.

        Parameters
        ----------
        dataset : h5py.Dataset

        Returns
        -------
        pd.DatetimeIndex

        """
        length = dataset.attrs["length"]
        return make_timestamps(dataset[:length])
