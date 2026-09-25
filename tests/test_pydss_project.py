import datetime
import os
import re
import shutil
import tempfile

import pandas as pd
import pytest

from pydss.common import PROJECT_TAR, PROJECT_ZIP
from pydss.exceptions import InvalidParameter
from pydss.pydss_fs_interface import SCENARIOS
from pydss.pydss_project import PyDssProject, PyDssScenario, DATA_FORMAT_VERSION
from pydss.pydss_results import PyDssResults, PyDssScenarioResults
from tests.common import RUN_PROJECT_PATH
from pydss.common import SIMULATION_SETTINGS_FILENAME


PATH = os.path.join(tempfile.gettempdir(), "pydss-projects")


@pytest.fixture
def pydss_project():
    if os.path.exists(PATH):
        shutil.rmtree(PATH)
    yield
    if os.path.exists(PATH):
        shutil.rmtree(PATH)


def test_create_project(pydss_project):
    project_name = "test-project"
    project_dir = os.path.join(PATH, project_name)
    # Intentionally not in alphabetic order so that we verify our designated
    # ordering.
    scenarios = [
        PyDssScenario("b_scenario1"),
        PyDssScenario("a_scenario2"),
    ]
    project = PyDssProject.create_project(PATH, project_name, scenarios)
    assert os.path.exists(project_dir)
    for dir_name in PyDssScenario._SCENARIO_DIRECTORIES:
        for scenario in scenarios:
            path = os.path.join(
                project_dir,
                SCENARIOS,
                scenario.name,
                dir_name,
            )
            assert os.path.exists(path)

    project2 = PyDssProject.load_project(project_dir)
    assert project.name == project2.name
    scenarios1 = project.scenarios
    scenarios1.sort(key=lambda x: x.name)
    scenarios2 = project2.scenarios
    scenarios2.sort(key=lambda x: x.name)

    assert len(scenarios1) == len(scenarios2)
    for i in range(len(project.scenarios)):
        assert scenarios1[i].name == scenarios2[i].name
        assert scenarios1[i].controllers == scenarios2[i].controllers


EXPECTED_ELEM_CLASSES_PROPERTIES = {
    "Loads": ["Powers"],
    "Storages": ["Powers"],
    "Buses": ["puVmagAngle", "Distance"],
    "Circuits": ["TotalPower", "LineLosses", "Losses", "SubstationLosses"],
    "Lines": ["Currents", "CurrentsMagAng", "VoltagesMagAng", "NormalAmps"],
    "Transformers": ["Currents", "NormalAmps"],
}


def test_run_project_by_property_dirs(cleanup_project):
    run_test_project_by_property(tar_project=False, zip_project=False)


def test_run_project_by_property_tar(cleanup_project):
    run_test_project_by_property(tar_project=True, zip_project=False)
    assert os.path.exists(os.path.join(RUN_PROJECT_PATH, PROJECT_TAR))
    assert not os.path.exists(os.path.join(RUN_PROJECT_PATH, PROJECT_ZIP))
    assert not os.path.exists(os.path.join(RUN_PROJECT_PATH, "Exports"))


def test_run_project_by_property_zip(cleanup_project):
    run_test_project_by_property(tar_project=False, zip_project=True)
    assert os.path.exists(os.path.join(RUN_PROJECT_PATH, PROJECT_ZIP))
    assert not os.path.exists(os.path.join(RUN_PROJECT_PATH, PROJECT_TAR))
    assert not os.path.exists(os.path.join(RUN_PROJECT_PATH, "Exports"))


def test_run_project_by_property_err(cleanup_project):
    with pytest.raises(InvalidParameter):
        run_test_project_by_property(tar_project=True, zip_project=True)


def run_test_project_by_property(tar_project, zip_project):
    project = PyDssProject.load_project(RUN_PROJECT_PATH)
    PyDssProject.run_project(
        RUN_PROJECT_PATH,
        tar_project=tar_project,
        zip_project=zip_project,
        simulation_file=SIMULATION_SETTINGS_FILENAME,
    )

    results = PyDssResults(RUN_PROJECT_PATH)
    assert len(results.scenarios) == 1
    assert results._hdf_store.attrs["version"] == DATA_FORMAT_VERSION
    scenario = results.scenarios[0]
    print(scenario)

    assert isinstance(scenario, PyDssScenarioResults)
    elem_classes = scenario.list_element_classes()
    expected_elem_classes = list(EXPECTED_ELEM_CLASSES_PROPERTIES.keys())
    expected_elem_classes.sort()
    assert elem_classes == expected_elem_classes
    for elem_class in elem_classes:
        expected_properties = EXPECTED_ELEM_CLASSES_PROPERTIES[elem_class]
        expected_properties.sort()
        properties = scenario.list_element_properties(elem_class)
        assert properties == expected_properties
        for prop in properties:
            element_names = scenario.list_element_names(elem_class, prop)
            for name in element_names:
                df = scenario.get_dataframe(elem_class, prop, name)
                assert isinstance(df, pd.DataFrame)
                assert len(df) == 96
            for name, df in scenario.iterate_dataframes(elem_class, prop):
                assert name in element_names
                assert isinstance(df, pd.DataFrame)

    # Test with an option.
    assert scenario.list_element_property_options("Lines", "Currents") == ["phase_terminal"]
    df = scenario.get_dataframe("Lines", "Currents", "Line.sw0", phase_terminal="A1")
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 96
    assert len(df.columns) == 1
    step = datetime.timedelta(seconds=project.simulation_config.project.step_resolution_sec)
    assert df.index[1] - df.index[0] == step

    df = scenario.get_dataframe(
        "Lines", "CurrentsMagAng", "Line.sw0", phase_terminal="A1", mag_ang="mag"
    )
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 96
    assert len(df.columns) == 1

    df = scenario.get_dataframe(
        "Lines", "CurrentsMagAng", "Line.sw0", phase_terminal=None, mag_ang="ang"
    )
    assert isinstance(df, pd.DataFrame)
    assert len(df.columns) == 2
    assert len(df) == 96

    regex = re.compile(r"[ABCN]1")
    df = scenario.get_dataframe("Lines", "Currents", "Line.sw0", phase_terminal=regex)
    assert isinstance(df, pd.DataFrame)
    assert len(df.columns) == 1
    assert len(df) == 96

    option_values = scenario.get_option_values("Lines", "Currents", "Line.sw0")
    assert option_values == ["A1", "A2"]

    prop = "Currents"
    full_df = scenario.get_full_dataframe("Lines", prop)
    assert len(full_df.columns) >= len(scenario.list_element_names("Lines", prop))
    for column in full_df.columns:
        assert "Unnamed" not in column
    assert len(full_df) == 96

    element_info_files = scenario.list_element_info_files()
    assert element_info_files
    for filename in element_info_files:
        df = scenario.read_element_info_file(filename)
        assert isinstance(df, pd.DataFrame)

    # Test the shortcut.
    df = scenario.read_element_info_file("PVSystems")
    assert isinstance(df, pd.DataFrame)

    scenario.read_capacitor_changes()
