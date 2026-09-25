from pathlib import Path
import tempfile
import shutil
import os

import pandas as pd
import pytest
import h5py
import mock

from pydss.export_list_reader import ExportListProperty
from pydss.dataset_buffer import DatasetBuffer
from pydss.metrics import ExportPowersMetric
from pydss.simulation_input_models import create_simulation_settings, load_simulation_settings
from tests.common import FakeElement

OBJS = [
    FakeElement("Line.one", "one"),
    FakeElement("Line.two", "two"),
    FakeElement("Load.one", "one"),
    FakeElement("Load.two", "two"),
    FakeElement("PVSystem.one", "one"),
    FakeElement("PVSystem.two", "two"),
    FakeElement("Transformer.ONE", "one"),
    FakeElement("Transformer.TWO", "two"),
]
STORE_FILENAME = os.path.join(tempfile.gettempdir(), "store.h5")
EXPORTED_POWERS_BASE_FILENAME = "tests/data/exported_powers/FEEDER_EXP_POWERS"
NUM_POWERS_FILES = 3
LOAD_1_VALUES = [1.4, 1.8, 1.7]
LOAD_2_VALUES = [2.1, 2.9, 2.4]
PV_SYSTEM_1_VALUES = [10.1, 11.5, 11.1]
PV_SYSTEM_2_VALUES = [7.4, 7.9, 7.7]


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


powers_file_id = 1


def mock_run_command():
    filename = f"{EXPORTED_POWERS_BASE_FILENAME}{powers_file_id}.CSV"
    return filename


@mock.patch("pydss.metrics.OpenDssExportMetric._run_command", side_effect=mock_run_command)
def test_export_powers(mocked_func, simulation_settings):
    data1 = {
        "property": "ExportPowersMetric",
        "store_values_type": "all",
        "opendss_classes": ["Lines", "Loads", "PVSystems", "Transformers"],
    }
    prop1 = ExportListProperty("CktElement", data1)
    data2 = {
        "property": "ExportPowersMetric",
        "store_values_type": "max",
        "opendss_classes": ["Lines", "Loads", "PVSystems", "Transformers"],
    }
    prop2 = ExportListProperty("CktElement", data2)
    data3 = {
        "property": "ExportPowersMetric",
        "store_values_type": "sum",
        "opendss_classes": ["Lines", "Loads", "PVSystems", "Transformers"],
    }
    prop3 = ExportListProperty("CktElement", data3)
    num_time_steps = NUM_POWERS_FILES
    metric = ExportPowersMetric(prop1, OBJS, simulation_settings)
    metric.add_property(prop2)
    metric.add_property(prop3)
    with h5py.File(STORE_FILENAME, mode="w", driver="core") as hdf_store:
        metric.initialize_data_store(hdf_store, "", num_time_steps)
        global powers_file_id
        for i in range(num_time_steps):
            metric.append_values(i)
            powers_file_id += 1
        metric.close()

        dataset1 = hdf_store["CktElement/ElementProperties/ExportPowersMetric"]
        assert dataset1.attrs["length"] == num_time_steps
        assert dataset1.attrs["type"] == "per_time_point"
        df = DatasetBuffer.to_dataframe(dataset1)
        assert isinstance(df, pd.DataFrame)
        assert [x for x in df["Load.one__Powers"].values] == LOAD_1_VALUES
        assert [x for x in df["Load.two__Powers"].values] == LOAD_2_VALUES
        assert [x for x in df["PVSystem.one__Powers"].values] == PV_SYSTEM_1_VALUES
        assert [x for x in df["PVSystem.two__Powers"].values] == PV_SYSTEM_2_VALUES

        dataset2 = hdf_store["CktElement/ElementProperties/ExportPowersMetricMax"]
        assert dataset2.attrs["length"] == 1
        assert dataset2.attrs["type"] == "value"
        # Loads are at the index 2, PVSystems at 4
        assert dataset2[0][2] == max(LOAD_1_VALUES)
        assert dataset2[0][3] == max(LOAD_2_VALUES)
        assert dataset2[0][4] == max(PV_SYSTEM_1_VALUES)
        assert dataset2[0][5] == max(PV_SYSTEM_2_VALUES)

        dataset3 = hdf_store["CktElement/ElementProperties/ExportPowersMetricSum"]
        assert dataset3.attrs["length"] == 1
        assert dataset3.attrs["type"] == "value"
        assert dataset3[0][2] == sum(LOAD_1_VALUES)
        assert dataset3[0][3] == sum(LOAD_2_VALUES)
        assert dataset3[0][4] == sum(PV_SYSTEM_1_VALUES)
        assert dataset3[0][5] == sum(PV_SYSTEM_2_VALUES)
