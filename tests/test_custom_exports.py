import math
import os


import numpy as np
import pandas as pd


from pydss.utils.utils import load_data
from pydss.pydss_project import PyDssProject
from pydss.pydss_results import PyDssResults
from tests.common import (
    run_project_with_custom_exports,
    CUSTOM_EXPORTS_PROJECT_PATH,
)
from pydss.common import SIMULATION_SETTINGS_FILENAME


def test_custom_exports(cleanup_project):
    _get_all_node_voltages()

    PyDssProject.run_project(
        CUSTOM_EXPORTS_PROJECT_PATH,
        simulation_file=SIMULATION_SETTINGS_FILENAME,
    )
    results = PyDssResults(CUSTOM_EXPORTS_PROJECT_PATH)
    assert len(results.scenarios) == 1
    scenario = results.scenarios[0]

    # Property stored at all time points.
    df = scenario.get_full_dataframe("Buses", "puVmagAngle")
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 96

    # Property stored with a moving average.
    df = scenario.get_dataframe("Buses", "DistanceAvg", "t9")
    assert isinstance(df, pd.DataFrame)
    assert len(df) == int(96)
    # assert len(df) == int(96 / 5)
    for val in df.iloc[9:, 0]:
        assert round(val, 3) == 0.082

    # TODO DT: these values are no longer correct. What should they be?
    # Filtered value on custom function.
    # df = scenario.get_dataframe("Lines", "LoadingPercent", "Line.sl_22")
    # assert len(df) == 14

    # df = scenario.get_dataframe("Lines", "LoadingPercentAvg", "Line.sl_22")
    # This was computed from raw data.
    # assert len(df) == 9
    # TODO incorrect after more decimal points
    # assert round(df.iloc[:, 0].values[8], 2) == 22.79

    # Subset of names. VoltagesMagAng has specific names, CurrentsMagAng has regex
    for name in ("Line.pvl_110", "Line.pvl_111", "Line.pvl_112", "Line.pvl_113"):
        properties = scenario.list_element_properties("Lines", element_name=name)
        assert "VoltagesMagAng" in properties
        assert "CurrentsMagAng" in properties

    properties = scenario.list_element_properties("Lines", element_name="Line.SL_14")
    assert "VoltagesMagAng" not in properties
    assert "CurrentsMagAng" not in properties

    # TODO: This metric no longer stores voltages in a dataframe.
    # That functionality could be recovered in PyDSS/metrics.py or we could implement this with
    # a different export property.
    # node_names = scenario.list_element_names("Nodes", "VoltageMetric")
    # dfs = scenario.get_filtered_dataframes("Nodes", "VoltageMetric")
    # assert len(node_names) == len(dfs)
    # assert sorted(node_names) == sorted(dfs.keys())
    # for i, node_name in enumerate(node_names):
    #    column = node_name + "__Voltage"
    #    df = dfs[node_name]
    #    # TODO: Slight rounding errors make this intermittent.
    #    #expected = all_node_voltages[column]
    #    #expected = expected[(expected < 1.02) | (expected > 1.04)]
    #    #assert len(df[column]) == len(expected)
    #    #assert_series_equal(df[column], expected, check_names=False)
    #    df2 = scenario.get_dataframe("Nodes", "VoltageMetric", node_name)
    #    assert_series_equal(df[column], df2[column], check_names=False)

    ## Two types of sums are stored.
    normal_amps_sum = scenario.get_element_property_value("Lines", "NormalAmpsSum", "Line.pvl_110")
    assert normal_amps_sum == 96 * 65.0
    scenario.get_element_property_value("Lines", "CurrentsSum", "Line.pvl_110")
    scenario.get_element_property_value("Circuits", "LossesSum", "Circuit.heco19021")

    sums_json = os.path.join(
        CUSTOM_EXPORTS_PROJECT_PATH, "Exports", "scenario1", "element_property_values.json"
    )
    assert os.path.exists(sums_json)
    data = load_data(sums_json)
    assert data

    pv_profiles = scenario.read_pv_profiles()
    assert pv_profiles["pv_systems"]
    for info in pv_profiles["pv_systems"]:
        assert isinstance(info["name"], str)
        assert isinstance(info["irradiance"], float)
        assert isinstance(info["pmpp"], float)
        assert isinstance(info["load_shape_profile"], str)
        assert isinstance(info["load_shape_pmult_sum"], float)


def test_export_moving_averages(cleanup_project):
    # Compares the moving average storage/calculation with a rolling average
    # computed on dataset with every time point.
    path = CUSTOM_EXPORTS_PROJECT_PATH
    sim_file = SIMULATION_SETTINGS_FILENAME
    circuit = "Circuit.heco19021"
    window_size = 10
    PyDssProject.run_project(path, simulation_file=sim_file)

    # This DataFrame will have values at every time point.
    df1 = _get_dataframe(path, "Circuits", "LineLosses", circuit, real_only=True)
    assert len(df1) == 96
    df1_rm = df1.rolling(window_size).mean()

    data = {
        "Circuits": {
            "LineLosses": {
                "store_values_type": "moving_average",
                "window_size": window_size,
            },
        }
    }
    run_project_with_custom_exports(path, "scenario1", sim_file, data)
    results = PyDssResults(path)
    assert len(results.scenarios) == 1
    results.scenarios[0]

    # This DataFrame will have moving averages.
    df2 = _get_dataframe(path, "Circuits", "LineLossesAvg", circuit, real_only=True)
    assert len(df2) == 96

    for val1, val2 in zip(df1_rm.iloc[:, 0].values, df2.iloc[:, 0].values):
        if np.isnan(val1):
            assert np.isnan(val2)
        else:
            assert round(val2, 5) == round(val1, 5)


def test_pv_powers_by_customer_type(cleanup_project):
    """Verify that PVSystem power output values collected by all variations match."""
    path = CUSTOM_EXPORTS_PROJECT_PATH
    PyDssProject.run_project(path, simulation_file=SIMULATION_SETTINGS_FILENAME)
    com_pv_systems = set(["pvgnem_mpx000635970", "pvgnem_mpx000460267"])
    res_pv_systems = set(["pvgnem_mpx000594341", "pvgui_mpx000637601", "pvgui_mpx000460267"])

    # Collect power for every PVSystem at every time point.
    df = _get_full_dataframe(path, "PVSystems", "Powers")
    com_cols, res_cols = _get_customer_type_columns(df, com_pv_systems, res_pv_systems)
    com_sum1 = df[com_cols].sum().sum()
    res_sum1 = df[res_cols].sum().sum()
    total_sum1 = df.sum().sum()
    assert math.isclose(abs(total_sum1), abs(com_sum1 + res_sum1))

    # Collect a running sum for all PVSystem power output.
    data = {
        "PVSystems": {
            "Powers": {
                "store_values_type": "sum",
                "sum_elements": True,
            },
        }
    }
    run_project_with_custom_exports(path, "scenario1", SIMULATION_SETTINGS_FILENAME, data)
    total_sum2 = sum(_get_summed_element_total(path, "PVSystems", "PowersSum").values())
    assert math.isclose(total_sum1.real, total_sum2.real) and math.isclose(
        total_sum1.imag, total_sum2.imag
    )

    # Collect power for PVSystems aggregated by customer type at every time point.
    data = {
        "PVSystems": {
            "Powers": {
                "store_values_type": "all",
                "sum_groups": [
                    {
                        "name": "com",
                        "elements": list(com_pv_systems),
                    },
                    {
                        "name": "res",
                        "elements": list(res_pv_systems),
                    },
                ],
            },
        }
    }
    run_project_with_custom_exports(path, "scenario1", SIMULATION_SETTINGS_FILENAME, data)
    com_sum3 = _get_summed_element_dataframe(path, "PVSystems", "Powers", group="com").sum().sum()
    res_sum3 = _get_summed_element_dataframe(path, "PVSystems", "Powers", group="res").sum().sum()
    assert math.isclose(com_sum1.real, com_sum3.real) and math.isclose(com_sum1.imag, com_sum3.imag)
    assert math.isclose(res_sum1.real, res_sum3.real) and math.isclose(res_sum1.imag, res_sum3.imag)

    # Collect a running sum for all PVSystems by customer type.
    data = {
        "PVSystems": {
            "Powers": {
                "store_values_type": "sum",
                "sum_groups": [
                    {
                        "name": "com",
                        "elements": list(com_pv_systems),
                    },
                    {
                        "name": "res",
                        "elements": list(res_pv_systems),
                    },
                ],
            },
        }
    }
    run_project_with_custom_exports(path, "scenario1", SIMULATION_SETTINGS_FILENAME, data)
    com_sum4 = sum(_get_summed_element_total(path, "PVSystems", "PowersSum", group="com").values())
    res_sum4 = sum(_get_summed_element_total(path, "PVSystems", "PowersSum", group="res").values())
    assert math.isclose(com_sum1.real, com_sum4.real) and math.isclose(com_sum1.imag, com_sum4.imag)
    assert math.isclose(res_sum1.real, res_sum4.real) and math.isclose(res_sum1.imag, res_sum4.imag)


def _get_customer_type_columns(df, com_pv_systems, res_pv_systems):
    com_cols = []
    res_cols = []
    for col in df.columns:
        for pv_system in com_pv_systems:
            if pv_system in col:
                com_cols.append(col)
                break
        for pv_system in res_pv_systems:
            if pv_system in col:
                res_cols.append(col)
                break

    return com_cols, res_cols


def _get_dataframe(path, elem_class, prop, name, **kwargs):
    return _get_data_common("get_dataframe", path, elem_class, prop, name, **kwargs)


def _get_full_dataframe(path, elem_class, prop, **kwargs):
    return _get_data_common("get_full_dataframe", path, elem_class, prop, **kwargs)


def _get_summed_element_dataframe(path, elem_class, prop, **kwargs):
    return _get_data_common("get_summed_element_dataframe", path, elem_class, prop, **kwargs)


def _get_summed_element_total(path, elem_class, prop, **kwargs):
    return _get_data_common("get_summed_element_total", path, elem_class, prop, **kwargs)


def _get_data_common(method_name, path, *args, **kwargs):
    results = PyDssResults(path)
    assert len(results.scenarios) == 1
    scenario = results.scenarios[0]
    method = getattr(scenario, method_name)
    return method(*args, **kwargs)


def _get_all_node_voltages():
    data = {
        "Nodes": {
            "VoltageMetric": {
                "store_values_type": "all",
                "limits": [1.02, 1.04],
                "limits_b": [1.01, 1.05],
            },
        }
    }
    path = CUSTOM_EXPORTS_PROJECT_PATH
    sim_file = SIMULATION_SETTINGS_FILENAME
    run_project_with_custom_exports(path, "scenario1", sim_file, data)
    results = PyDssResults(path)
    assert len(results.scenarios) == 1
    results.scenarios[0]
