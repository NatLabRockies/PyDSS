from pathlib import Path
import tempfile
import shutil
import os

from loguru import logger
import pandas as pd
import numpy as np
import pytest
import h5py

from pydss.value_storage import ValueByNumber, ValueByList
from pydss.export_list_reader import ExportListProperty
from pydss.metrics import MultiValueTypeMetricBase
from pydss.dataset_buffer import DatasetBuffer
from pydss.simulation_input_models import create_simulation_settings, load_simulation_settings
from pydss.common import LimitsFilter
from tests.common import FakeElement


STORE_FILENAME = os.path.join(tempfile.gettempdir(), "store.h5")
FLOATS = (1.0, 2.0, 3.0, 4.0, 5.0)
COMPLEX_NUMS = (
    complex(1, 2),
    complex(3, 4),
    complex(5, 6),
    complex(7, 8),
    complex(9, 10),
)
LIST_COMPLEX_NUMS = (
    [complex(1, 2), complex(3, 4)],
    [complex(5, 6), complex(7, 8)],
    [complex(9, 10), complex(11, 12)],
    [complex(13, 14), complex(15, 16)],
    [complex(17, 18), complex(19, 20)],
)

OBJS = [
    FakeElement("Fake.a", "a"),
    FakeElement("Fake.b", "b"),
]


@pytest.fixture
def simulation_settings():
    project_path = Path(tempfile.gettempdir()) / "pydss_projects"
    if project_path.exists():
        shutil.rmtree(project_path)
    project_name = "test_project"
    project_path.mkdir()
    filename = create_simulation_settings(project_path, project_name, ["s1"])
    yield load_simulation_settings(filename)
    if os.path.exists(STORE_FILENAME):
        os.remove(STORE_FILENAME)
    if project_path.exists():
        shutil.rmtree(project_path)


class FakeMetric(MultiValueTypeMetricBase):
    def __init__(self, prop, dss_objs, options, values):
        super().__init__(prop, dss_objs, options)
        self._elem_index = 0
        self._val_index = 0
        self._values = values

    def _get_value(self, obj, timestamp):
        prop = next(iter(self._properties.values()))
        if isinstance(self._values[self._val_index], list):
            val = ValueByList(obj.FullName, prop.name, self._values[self._val_index], ["", ""])
        else:
            val = ValueByNumber(obj.FullName, prop.name, self._values[self._val_index])
        logger.debug(
            "elem_index=%s val_index=%s, val=%s", self._elem_index, self._val_index, val.value
        )
        self._elem_index += 1
        if self._elem_index == len(self._dss_objs):
            self._elem_index = 0
            # Change values once we've iterated through all elements.
            self._val_index += 1
            if self._val_index == len(self._values):
                self._val_index = 0
        return val


def test_metrics_store_all(simulation_settings):
    data = {
        "property": "Property",
        "store_values_type": "all",
    }
    values = FLOATS
    prop = ExportListProperty("Fake", data)
    metric = FakeMetric(prop, OBJS, simulation_settings, values)
    with h5py.File(STORE_FILENAME, mode="w", driver="core") as hdf_store:
        metric.initialize_data_store(hdf_store, "", len(values))
        for i in range(len(values)):
            metric.append_values(i)
        metric.close()

        dataset = hdf_store["Fake/ElementProperties/Property"]
        assert dataset.attrs["length"] == len(values)
        assert dataset.attrs["type"] == "per_time_point"
        df = DatasetBuffer.to_dataframe(dataset)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == len(values)
        for column in df.columns:
            for val1, val2 in zip(df[column].values, values):
                assert val1 == val2
        assert metric.max_num_bytes() == len(values) * len(OBJS) * 8


def test_metrics_store_all_complex_abs(simulation_settings):
    data = {
        "property": "Property",
        "store_values_type": "all",
        "data_conversion": "abs",
    }
    values = COMPLEX_NUMS
    prop = ExportListProperty("Fake", data)
    metric = FakeMetric(prop, OBJS, simulation_settings, values)
    with h5py.File(STORE_FILENAME, mode="w", driver="core") as hdf_store:
        metric.initialize_data_store(hdf_store, "", len(values))
        for i in range(len(values)):
            metric.append_values(i)
        metric.close()

        dataset = hdf_store["Fake/ElementProperties/Property"]
        assert dataset.attrs["length"] == len(values)
        assert dataset.attrs["type"] == "per_time_point"
        df = DatasetBuffer.to_dataframe(dataset)
        assert len(df) == len(values)
        for column in df.columns:
            for val1, val2 in zip(df[column].values, values):
                assert isinstance(val1, float)
                assert val1 == abs(val2)


def test_metrics_store_all_complex_sum(simulation_settings):
    data = {
        "property": "Property",
        "store_values_type": "all",
        "data_conversion": "sum",
    }
    values = LIST_COMPLEX_NUMS
    prop = ExportListProperty("Fake", data)
    metric = FakeMetric(prop, OBJS, simulation_settings, values)
    with h5py.File(STORE_FILENAME, mode="w", driver="core") as hdf_store:
        metric.initialize_data_store(hdf_store, "", len(values))
        for i in range(len(values)):
            metric.append_values(i)
        metric.close()

        dataset = hdf_store["Fake/ElementProperties/Property"]
        assert dataset.attrs["length"] == len(values)
        assert dataset.attrs["type"] == "per_time_point"
        df = DatasetBuffer.to_dataframe(dataset)
        assert len(df) == len(values)
        for column in df.columns:
            for val1, val2 in zip(df[column].values, values):
                assert isinstance(val1, complex)
                assert val1 == sum(val2)


def test_metrics_store_all_complex_abs_sum(simulation_settings):
    data = {
        "property": "Property",
        "store_values_type": "all",
        "data_conversion": "abs_sum",
    }
    values = LIST_COMPLEX_NUMS
    prop = ExportListProperty("Fake", data)
    metric = FakeMetric(prop, OBJS, simulation_settings, values)
    with h5py.File(STORE_FILENAME, mode="w", driver="core") as hdf_store:
        metric.initialize_data_store(hdf_store, "", len(values))
        for i in range(len(values)):
            metric.append_values(i)
        metric.close()

        dataset = hdf_store["Fake/ElementProperties/Property"]
        assert dataset.attrs["length"] == len(values)
        assert dataset.attrs["type"] == "per_time_point"
        df = DatasetBuffer.to_dataframe(dataset)
        assert len(df) == len(values)
        for column in df.columns:
            for val1, val2 in zip(df[column].values, values):
                assert isinstance(val1, float)
                assert val1 == abs(sum(val2))


def test_metrics_store_all_filtered(simulation_settings):
    data = {
        "property": "Property",
        "store_values_type": "all",
        "limits": [1.0, 3.0],
        "limits_filter": LimitsFilter.OUTSIDE,
    }
    values = FLOATS
    prop = ExportListProperty("Fake", data)
    metric = FakeMetric(prop, OBJS, simulation_settings, values)
    with h5py.File(STORE_FILENAME, mode="w", driver="core") as hdf_store:
        metric.initialize_data_store(hdf_store, "", len(values))
        for i in range(len(values)):
            metric.append_values(i)
        metric.close()

        dataset = hdf_store["Fake/ElementProperties/Property"]
        assert dataset.attrs["length"] == 2 * len(OBJS)
        assert dataset.attrs["type"] == "filtered"
        assert [x for x in dataset[:4]] == [4, 4, 5, 5]
        time_step_dataset = hdf_store["Fake/ElementProperties/PropertyTimeStep"]
        assert time_step_dataset.attrs["type"] == "time_step"
        assert time_step_dataset.attrs["length"] == 4
        assert [x for x in time_step_dataset[0]] == [3, 0]
        assert [x for x in time_step_dataset[1]] == [3, 1]
        assert [x for x in time_step_dataset[2]] == [4, 0]
        assert [x for x in time_step_dataset[3]] == [4, 1]


def test_metrics_store_moving_average_and_max(simulation_settings):
    window_size = 10
    values = [float(i) for i in range(50)] + [float(i) for i in range(25)]
    data1 = {
        "property": "Property",
        "store_values_type": "max",
    }
    data2 = {
        "property": "Property",
        "store_values_type": "moving_average",
        "window_size": window_size,
    }
    prop1 = ExportListProperty("Fake", data1)
    prop2 = ExportListProperty("Fake", data2)
    metric = FakeMetric(prop1, OBJS, simulation_settings, values)
    metric.add_property(prop2)

    base_df = pd.DataFrame(values)
    base_series = base_df.iloc[:, 0]
    base_rm = base_series.rolling(window_size).mean()

    with h5py.File(STORE_FILENAME, mode="w", driver="core") as hdf_store:
        metric.initialize_data_store(hdf_store, "", len(values))
        for i in range(len(values)):
            metric.append_values(i)
        metric.close()

        dataset1 = hdf_store["Fake/ElementProperties/PropertyMax"]
        assert dataset1.attrs["length"] == 1
        assert dataset1.attrs["type"] == "value"
        assert dataset1[0][0] == 49
        assert dataset1[0][1] == 49

        dataset2 = hdf_store["Fake/ElementProperties/PropertyAvg"]
        assert dataset2.attrs["length"] == len(values)
        assert dataset2.attrs["type"] == "per_time_point"
        df = DatasetBuffer.to_dataframe(dataset2)
        assert len(df) == len(values)
        for column in df.columns:
            for val1, val2 in zip(df[column].values, base_rm.values):
                if np.isnan(val1):
                    assert np.isnan(val2)
                else:
                    assert val1 == val2


def test_metrics_store_moving_average_with_limits(simulation_settings):
    limits = [1.0, 50.0]
    window_size = 10
    data = {
        "property": "Property",
        "store_values_type": "moving_average",
        "window_size": window_size,
        "limits": limits,
        "limits_filter": LimitsFilter.OUTSIDE,
    }
    values = [float(x) for x in range(1, 101)]
    [x for x in values if x < limits[0] or x > limits[1]]
    base_df = pd.DataFrame(values)
    base_series = base_df.iloc[:, 0]
    base_rm = base_series.rolling(window_size).mean()
    expected = [x for x in base_rm.values if x < limits[0] or x > limits[1]]
    prop = ExportListProperty("Fake", data)
    metric = FakeMetric(prop, OBJS, simulation_settings, values)
    with h5py.File(STORE_FILENAME, mode="w", driver="core") as hdf_store:
        metric.initialize_data_store(hdf_store, "", len(values))
        for i in range(len(values)):
            metric.append_values(i)
        metric.close()

        dataset = hdf_store["Fake/ElementProperties/PropertyAvg"]
        assert dataset.attrs["length"] == len(expected) * len(OBJS)
        assert dataset.attrs["type"] == "filtered"
        time_step_dataset = hdf_store["Fake/ElementProperties/PropertyAvgTimeStep"]
        assert time_step_dataset.attrs["type"] == "time_step"
        assert time_step_dataset.attrs["length"] == dataset.attrs["length"]
        for i, expected_val in enumerate(expected):
            assert dataset[i * 2] == expected_val
            assert dataset[i * 2 + 1] == expected_val


def test_metrics_store_moving_average_max(simulation_settings):
    window_size = 10
    data = {
        "property": "Property",
        "store_values_type": "moving_average_max",
        "window_size": window_size,
    }
    values = [float(i) for i in range(100)]
    base_df = pd.DataFrame(values)
    base_series = base_df.iloc[:, 0]
    base_rm = base_series.rolling(window_size).mean()
    prop = ExportListProperty("Fake", data)
    metric = FakeMetric(prop, OBJS, simulation_settings, values)
    with h5py.File(STORE_FILENAME, mode="w", driver="core") as hdf_store:
        metric.initialize_data_store(hdf_store, "", len(values))
        for i in range(len(values)):
            metric.append_values(i)
        metric.close()

        dataset = hdf_store["Fake/ElementProperties/PropertyAvgMax"]
        assert dataset.attrs["length"] == 1
        assert dataset.attrs["type"] == "value"
        assert dataset[0][0] == base_rm.max()
        assert dataset[0][1] == dataset[0][0]
        assert metric.max_num_bytes() == 8 * len(OBJS)


def test_metrics_store_sum(simulation_settings):
    data = {
        "property": "Property",
        "store_values_type": "sum",
    }
    values = FLOATS
    prop = ExportListProperty("Fake", data)
    metric = FakeMetric(prop, OBJS, simulation_settings, values)
    with h5py.File(STORE_FILENAME, mode="w", driver="core") as hdf_store:
        metric.initialize_data_store(hdf_store, "", len(values))
        for i in range(len(values)):
            metric.append_values(i)
        metric.close()

        dataset = hdf_store["Fake/ElementProperties/PropertySum"]
        assert dataset.attrs["length"] == 1
        assert dataset.attrs["type"] == "value"
        assert len(dataset[0]) == 2
        assert dataset[0][0] == sum(values)
        assert dataset[0][1] == sum(values)
        assert metric.max_num_bytes() == 8 * len(OBJS)


def test_metrics_store_max(simulation_settings):
    data = {
        "property": "Property",
        "store_values_type": "max",
    }
    values = FLOATS
    prop = ExportListProperty("Fake", data)
    metric = FakeMetric(prop, OBJS, simulation_settings, values)
    with h5py.File(STORE_FILENAME, mode="w", driver="core") as hdf_store:
        metric.initialize_data_store(hdf_store, "", len(values))
        for i in range(len(values)):
            metric.append_values(i)
        metric.close()

        dataset = hdf_store["Fake/ElementProperties/PropertyMax"]
        assert dataset.attrs["length"] == 1
        assert dataset.attrs["type"] == "value"
        assert len(dataset[0]) == 2
        assert dataset[0][0] == max(values)
        assert dataset[0][1] == max(values)
        assert metric.max_num_bytes() == 8 * len(OBJS)


def test_metrics_store_min(simulation_settings):
    data = {
        "property": "Property",
        "store_values_type": "min",
    }
    values = FLOATS
    prop = ExportListProperty("Fake", data)
    metric = FakeMetric(prop, OBJS, simulation_settings, values)
    with h5py.File(STORE_FILENAME, mode="w", driver="core") as hdf_store:
        metric.initialize_data_store(hdf_store, "", len(values))
        for i in range(len(values)):
            metric.append_values(i)
        metric.close()

        dataset = hdf_store["Fake/ElementProperties/PropertyMin"]
        assert dataset.attrs["length"] == 1
        assert dataset.attrs["type"] == "value"
        assert len(dataset[0]) == 2
        assert dataset[0][0] == min(values)
        assert dataset[0][1] == min(values)
        assert metric.max_num_bytes() == 8 * len(OBJS)
