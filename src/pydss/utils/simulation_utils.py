
from datetime import timedelta
from collections import deque
import time

import opendssdirect as dss
import pandas as pd
import numpy as np

from pydss.simulation_input_models import SimulationSettingsModel
from pydss.common import TIME_FORMAT

class CircularBufferHelper:
    def __init__(self, window_size):
        self._buf = deque(maxlen=window_size)
        self._window_size = window_size

    def __len__(self):
        return len(self._buf)

    def append(self, val):
        self._buf.append(val)

    def average(self):
        if len(self._buf) < self._window_size:
            return np.nan
        return sum(self._buf) / len(self._buf)


class SimulationFilteredTimeRange:
    """Provides filtering in a time range."""
    def __init__(self, start, end):
        self._start = time.strptime(start, TIME_FORMAT)
        self._end = time.strptime(end, TIME_FORMAT)
        default_start = time.strptime("00:00:00", TIME_FORMAT)
        default_end = time.strptime("11:59:59", TIME_FORMAT)
        self._no_filtering = start == default_start and end == default_end

    @classmethod
    def from_settings(cls, settings: SimulationSettingsModel):
        """Return SimulationFilteredTimeRange from the simulation settings.

        Parameters
        ----------
        settings : dict
            settings from project simulation.toml

        Returns
        -------
        SimulationFilteredTimeRange

        """
        return cls(
            start=settings.project.simulation_range.start,
            end=settings.project.simulation_range.end,
        )

    def is_within_range(self, timestamp):
        """Return True if the timestamp is within the filtered range.

        Parameters
        ----------
        timestamp : datetime

        Returns
        -------
        bool

        """
        if self._no_filtering:
            return True

        ts = time.struct_time((
            self._start.tm_year, self._start.tm_mon, self._start.tm_mday, timestamp.hour,
            timestamp.minute, timestamp.second, self._start.tm_wday, self._start.tm_yday,
            self._start.tm_isdst
        ))
        return ts >= self._start and ts <=self._end


def get_start_time(settings: SimulationSettingsModel):
    """Return the start time of the simulation.

    Parameters
    ----------
    settings : SimulationSettingsModel

    Returns
    -------
    datetime

    """
    return settings.project.start_time


def get_simulation_resolution(settings: SimulationSettingsModel):
    """Return the simulation of the resolution

    Parameters
    ----------
    settings : SimulationSettingsModel

    Returns
    -------
    datetime

    """
    return timedelta(seconds=settings.project.step_resolution_sec)


def create_time_range_from_settings(settings: SimulationSettingsModel):
    """Return the start time, step time, and end time from the settings.

    Parameters
    ----------
    settings : SimulationSettingsModel

    Returns
    -------
    tuple
        (start, end, step)

    """
    start_time = get_start_time(settings)
    end_time = start_time + timedelta(minutes=settings.project.simulation_duration_min)
    step_time = get_simulation_resolution(settings)
    return start_time, end_time, step_time


def create_datetime_index_from_settings(settings: SimulationSettingsModel):
    """Return time indices created from the simulation settings.

    Parameters
    ----------
    settings : SimulationSettingsModel

    Returns
    -------
    pd.DatetimeIndex

    """
    start_time, end_time, step_time = create_time_range_from_settings(settings)
    data = []
    cur_time = start_time
    while cur_time < end_time:
        data.append(cur_time)
        cur_time += step_time

    return pd.DatetimeIndex(data)


def create_loadshape_pmult_dataframe(settings: SimulationSettingsModel):
    """Return a loadshape dataframe representing all available data.
    This assumes that a loadshape has been selected in OpenDSS.

    Parameters
    ----------
    settings : SimulationSettingsModel

    Returns
    -------
    pd.DatetimeIndex

    """
    start_time = settings.project.loadshape_start_time
    data = dss.LoadShape.PMult()
    interval = timedelta(seconds=dss.LoadShape.SInterval())
    npts = dss.LoadShape.Npts()

    indices = []
    cur_time = start_time
    for _ in range(npts):
        indices.append(cur_time)
        cur_time += interval

    return pd.DataFrame(data, index=pd.DatetimeIndex(indices))


def create_loadshape_pmult_dataframe_for_simulation(settings: SimulationSettingsModel):
    """Return a loadshape pmult dataframe that only contains time points used
    by the simulation.
    This assumes that a loadshape has been selected in OpenDSS.

    Parameters
    ----------
    settings : SimulationSettingsModel

    Returns
    -------
    pd.DataFrame

    """
    df = create_loadshape_pmult_dataframe(settings)
    simulation_index = create_datetime_index_from_settings(settings)
    return df.loc[simulation_index]
