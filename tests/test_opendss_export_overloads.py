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
from pydss.metrics import ExportLoadingsMetric
from pydss.simulation_input_models import create_simulation_settings, load_simulation_settings
from tests.common import FakeElement

OBJS = [
    FakeElement("Line.one", "one"),
    FakeElement("Line.two", "two"),
    FakeElement("Transformer.one", "one"),
    FakeElement("Transformer.two", "two"),
]
STORE_FILENAME = os.path.join(tempfile.gettempdir(), "store.h5")
EXPORTED_LOADINGS_BASE_FILENAME = "tests/data/exported_loadings/FEEDER_EXP_CAPACITY"
NUM_LOADINGS_FILES = 3
LINE_1_VALUES = [6.97, 2.75, 0.93]
LINE_2_VALUES = [1.19, 1.16, 11.44]
TRANSFORMER_1_VALUES = [8.60, 4.33, 12.82]
TRANSFORMER_2_VALUES = [12.10, 12.51, 28.79]


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


overloads_file_id = 1


def mock_run_command():
    filename = f"{EXPORTED_LOADINGS_BASE_FILENAME}{overloads_file_id}.CSV"
    return filename


@mock.patch("pydss.metrics.OpenDssExportMetric._run_command", side_effect=mock_run_command)
def test_export_overloads(mocked_func, simulation_settings):
    data1 = {
        "property": "ExportLoadingsMetric",
        "store_values_type": "all",
        "opendss_classes": ["Lines", "Transformers"],
    }
    prop1 = ExportListProperty("CktElement", data1)
    data2 = {
        "property": "ExportLoadingsMetric",
        "store_values_type": "max",
        "opendss_classes": ["Lines", "Transformers"],
    }
    prop2 = ExportListProperty("CktElement", data2)
    num_time_steps = NUM_LOADINGS_FILES
    metric = ExportLoadingsMetric(prop1, OBJS, simulation_settings)
    metric.add_property(prop2)
    with h5py.File(STORE_FILENAME, mode="w", driver="core") as hdf_store:
        metric.initialize_data_store(hdf_store, "", num_time_steps)
        global overloads_file_id
        for i in range(num_time_steps):
            metric.append_values(i)
            overloads_file_id += 1
        metric.close()

        dataset1 = hdf_store["CktElement/ElementProperties/ExportLoadingsMetric"]
        assert dataset1.attrs["length"] == num_time_steps
        assert dataset1.attrs["type"] == "per_time_point"
        df = DatasetBuffer.to_dataframe(dataset1)
        assert isinstance(df, pd.DataFrame)
        assert [x for x in df["Line.one__Loading"].values] == LINE_1_VALUES
        assert [x for x in df["Line.two__Loading"].values] == LINE_2_VALUES
        assert [x for x in df["Transformer.one__Loading"].values] == TRANSFORMER_1_VALUES
        assert [x for x in df["Transformer.two__Loading"].values] == TRANSFORMER_2_VALUES

        dataset2 = hdf_store["CktElement/ElementProperties/ExportLoadingsMetricMax"]
        assert dataset2.attrs["length"] == 1
        assert dataset2.attrs["type"] == "value"
        assert dataset2[0][0] == max(LINE_1_VALUES)
        assert dataset2[0][1] == max(LINE_2_VALUES)
        assert dataset2[0][2] == max(TRANSFORMER_1_VALUES)
        assert dataset2[0][3] == max(TRANSFORMER_2_VALUES)
