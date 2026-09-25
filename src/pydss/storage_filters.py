import copy
import abc

from loguru import logger
import numpy as np

from pydss.utils.simulation_utils import CircularBufferHelper
from pydss.value_storage import ValueContainer
from pydss.common import StoreValuesType


class StorageFilterBase(abc.ABC):
    """Base class for storage containers.
    Subclasses can perform custom filtering based on StoreValuesType.

    """

    def __init__(
        self, hdf_store, path, prop, num_steps, max_chunk_bytes, values, elem_names, **kwargs
    ):
        self._prop = prop
        self._container = self.make_container(
            hdf_store,
            path,
            prop,
            num_steps,
            max_chunk_bytes,
            values,
            elem_names,
        )
        logger.debug("Created %s path=%s", self.__class__.__name__, path)

    @abc.abstractmethod
    def append_values(self, values, time_step):
        """Store a new set of values for each element."""

    def close(self):
        """Perform any final writes to the container."""
        self.flush_data()

    def flush_data(self):
        """Flush data to disk."""
        self._container.flush_data()

    def max_num_bytes(self):
        """Return the maximum number of bytes the container could hold.

        Returns
        -------
        int

        """
        return self._container.max_num_bytes()

    @staticmethod
    def make_container(hdf_store, path, prop, num_steps, max_chunk_bytes, values, elem_names):
        """Return an instance of ValueContainer for storing values."""
        container = ValueContainer(
            values,
            hdf_store,
            path,
            prop.get_max_size(num_steps),
            elem_names,
            prop.get_dataset_property_type(),
            max_chunk_bytes=max_chunk_bytes,
            store_time_step=prop.should_store_time_step(),
        )
        logger.debug("Created storage container path=%s", path)
        return container


class StorageAll(StorageFilterBase):
    """Store values at every time point, optionally filtered."""

    def append_values(self, values, time_step):
        if self._prop.limits:
            for i, value in enumerate(values):
                if value.is_nan():
                    break
                if self._prop.should_store_value(value.value):
                    self._container.append_by_time_step(value, time_step, i)
        else:
            self._container.append(values)


"""
class StorageChangeCount(StorageFilterBase):
    def __init__(self, *args):
        super().__init__(*args)
        self._last_value = None
        self._change_count = (None, 0)

    def append_values(self, values, time_step):
        assert False
"""


class StorageMin(StorageFilterBase):
    """Stores the min value across time points."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._min = None

    def append_values(self, values, time_step):
        if values[0].is_nan():
            return
        self._handle_values(values)

    def close(self):
        if self._min is not None:
            self._container.append(self._min)
            self._container.flush_data()

    def _handle_values(self, values):
        if self._min is None:
            self._min = [copy.deepcopy(x) for x in values]
        else:
            for i, new_val in enumerate(values):
                cur_val = self._min[i]
                if (np.isnan(cur_val.value) and not np.isnan(new_val.value)) or new_val < cur_val:
                    self._min[i].set_value(new_val.value)


class StorageMax(StorageFilterBase):
    """Stores the max value across time points."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._max = None

    def append_values(self, values, time_step):
        if values[0].is_nan():
            return
        self._handle_values(values)

    def close(self):
        if self._max is not None:
            self._container.append(self._max)
            self._container.flush_data()

    def _handle_values(self, values):
        if self._max is None:
            self._max = [copy.deepcopy(x) for x in values]
        else:
            for i, new_val in enumerate(values):
                cur_val = self._max[i]
                if (np.isnan(cur_val.value) and not np.isnan(new_val.value)) or new_val > cur_val:
                    self._max[i].set_value(new_val.value)


class StorageMovingAverage(StorageFilterBase):
    """Stores a moving average across time points."""

    def __init__(self, *args, **kwargs):
        """Constructor for StorageMovingAverage.

        window_size comes from either the passed `prop` variable or an optional
        `window_sizes` keyword-argument variable. In the former case one size
        is applied to all elements being tracked. In the latter case
        `window_sizes` must be a list of integers that is a window_size for
        each corresponding element index.

        """
        super().__init__(*args, **kwargs)
        self._averages = None
        self._bufs = None
        self._window_sizes = kwargs.get("window_sizes")

    def append_values(self, values, time_step):
        if values[0].is_nan():
            return
        # Store every value in the circular buffer. Apply limits to the
        # moving average.
        if self._bufs is None:
            self._averages = [copy.deepcopy(x) for x in values]
            self._bufs = _make_circular_buffers(len(values), self._prop, self._window_sizes)

        for i, val in enumerate(values):
            buf = self._bufs[i]
            buf.append(val.value)
            self._averages[i].set_value(buf.average())

        if self._prop.limits:
            for i, avg in enumerate(self._averages):
                if self._prop.should_store_value(avg.value):
                    self._container.append_by_time_step(avg, time_step, i)
        else:
            self._container.append(self._averages)


class StorageMovingAverageMax(StorageMax):
    """Stores the max value of a moving average across time points."""

    def __init__(self, *args, **kwargs):
        """Constructor for StorageMovingAverageMax.

        window_size comes from either the passed `prop` variable or an optional
        `window_sizes` keyword-argument variable. In the former case one size
        is applied to all elements being tracked. In the latter case
        `window_sizes` must be a list of integers that is a window_size for
        each corresponding element index.

        """
        super().__init__(*args, **kwargs)
        self._bufs = None
        self._averages = None
        self._window_sizes = kwargs.get("window_sizes")

    def append_values(self, values, time_step):
        if values[0].is_nan():
            return
        if self._bufs is None:
            self._averages = [copy.deepcopy(x) for x in values]
            self._bufs = _make_circular_buffers(len(values), self._prop, self._window_sizes)

        for i, val in enumerate(values):
            buf = self._bufs[i]
            buf.append(val.value)
            self._averages[i].set_value(buf.average())

        self._handle_values(self._averages)


class StorageSum(StorageFilterBase):
    """Keeps a running sum of all values and records the total."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sum = None

    def append_values(self, values, _time_step):
        if values[0].is_nan():
            return
        if self._sum is None:
            self._sum = [copy.deepcopy(x) for x in values]
        else:
            for i, val in enumerate(values):
                self._sum[i] += val

    def close(self):
        if self._sum is not None:
            self._container.append(self._sum)
            self._container.flush_data()


def _make_circular_buffers(num_elements, prop, window_sizes):
    if window_sizes is None:
        window_size = prop.window_size
        bufs = [CircularBufferHelper(window_size) for _ in range(num_elements)]
    else:
        bufs = [CircularBufferHelper(window_sizes[i]) for i in range(num_elements)]
    return bufs


STORAGE_TYPE_MAP = {
    StoreValuesType.ALL: StorageAll,
    # StoreValuesType.CHANGE_COUNT: StorageChangeCount,
    StoreValuesType.MAX: StorageMax,
    StoreValuesType.MIN: StorageMin,
    StoreValuesType.MOVING_AVERAGE: StorageMovingAverage,
    StoreValuesType.MOVING_AVERAGE_MAX: StorageMovingAverageMax,
    StoreValuesType.SUM: StorageSum,
}
