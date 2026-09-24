

from pathlib import Path
import math
import os

import numpy as np

from tests.common import PV_REPORTS_PROJECT_PATH, PV_REPORTS_PROJECT_STORE_ALL_PATH, cleanup_project
from pydss.reports.feeder_losses import SimulationFeederLossesMetricsModel, compare_feeder_losses
from pydss.node_voltage_metrics import SimulationVoltageMetricsModel, compare_voltage_metrics
from pydss.thermal_metrics import SimulationThermalMetricsModel, compare_thermal_metrics
from pydss.utils.dataframe_utils import read_dataframe
from pydss.common import SIMULATION_SETTINGS_FILENAME
from pydss.reports.reports import ReportGranularity
from pydss.utils.utils import load_data, dump_data
from pydss.pydss_project import PyDssProject
from pydss.pydss_results import PyDssResults

import traceback
import warnings
import sys

def warn_with_traceback(message, category, filename, lineno, file=None, line=None):

    log = file if hasattr(file,'write') else sys.stderr
    traceback.print_stack(file=log)
    log.write(warnings.formatwarning(message, category, filename, lineno, line))

warnings.showwarning = warn_with_traceback

BASE_FILENAME = os.path.join(PV_REPORTS_PROJECT_PATH, SIMULATION_SETTINGS_FILENAME)
TEST_SIM_BASE_NAME = "test_sim.toml"
TEST_FILENAME = os.path.join(PV_REPORTS_PROJECT_PATH, TEST_SIM_BASE_NAME)
ARTIFACTS = (
    os.path.join(PV_REPORTS_PROJECT_PATH, "DSSfiles", "HECO19021_EXP_OVERLOADS.CSV"),
    os.path.join(PV_REPORTS_PROJECT_PATH, "DSSfiles", "HECO19021_EXP_POWERS.CSV"),
)


def test_pv_reports_per_element_per_time_point(cleanup_project):
    # Generates reports from data stored at every time point and then
    # use those to compare with the in-memory metrics.
    PyDssProject.run_project(
        PV_REPORTS_PROJECT_STORE_ALL_PATH,
        simulation_file=SIMULATION_SETTINGS_FILENAME,
    )

    baseline_thermal = SimulationThermalMetricsModel(
        **load_data(Path(PV_REPORTS_PROJECT_STORE_ALL_PATH) / "Reports" / "thermal_metrics.json")
    )
    baseline_voltage = SimulationVoltageMetricsModel(
        **load_data(Path(PV_REPORTS_PROJECT_STORE_ALL_PATH) / "Reports" / "voltage_metrics.json")
    )
    baseline_feeder_losses = SimulationFeederLossesMetricsModel(
        **load_data( Path(PV_REPORTS_PROJECT_STORE_ALL_PATH) / "Reports" / "feeder_losses.json")
    )

    granularities = [x for x in ReportGranularity]
    for granularity in granularities:
        settings = load_data(BASE_FILENAME)
        settings["Reports"]["Granularity"] = granularity.value
        dump_data(settings, TEST_FILENAME)
        try:
            PyDssProject.run_project(
                PV_REPORTS_PROJECT_PATH,
                simulation_file=TEST_SIM_BASE_NAME,
            )
            if granularity == ReportGranularity.PER_ELEMENT_PER_TIME_POINT:
                verify_skip_night()
                assert verify_thermal_metrics(baseline_thermal)
                assert verify_voltage_metrics(baseline_voltage)
                assert verify_feeder_losses(baseline_feeder_losses)
            verify_pv_reports(granularity)
            verify_feeder_head_metrics()
        finally:
            os.remove(TEST_FILENAME)
            for artifact in ARTIFACTS:
                if os.path.exists(artifact):
                    os.remove(artifact)


def verify_pv_reports(granularity):
    results = PyDssResults(PV_REPORTS_PROJECT_PATH)
    s_cm = results.scenarios[0]
    s_pf1 = results.scenarios[1]

    # This test data doesn't have changes for Capacitors or RegControls.
    capacitor_change_counts = results.read_report("Capacitor State Change Counts")
    assert len(capacitor_change_counts["scenarios"]) == 2
    assert not capacitor_change_counts["scenarios"][1]["capacitors"]

    reg_control_change_counts = results.read_report("RegControl Tap Number Change Counts")
    assert len(reg_control_change_counts["scenarios"]) == 2
    assert not reg_control_change_counts["scenarios"][1]["reg_controls"]

    if granularity in (
        ReportGranularity.PER_ELEMENT_PER_TIME_POINT,
        ReportGranularity.ALL_ELEMENTS_PER_TIME_POINT,
    ):
        clipping_name = os.path.join(PV_REPORTS_PROJECT_PATH, "Reports", "pv_clipping.h5")
        clipping = read_dataframe(clipping_name)
        curtailment_name = os.path.join(PV_REPORTS_PROJECT_PATH, "Reports", "pv_curtailment.h5")
        curtailment = read_dataframe(curtailment_name)
    else:
        clipping_name = os.path.join(PV_REPORTS_PROJECT_PATH, "Reports", "pv_clipping.json")
        clipping = load_data(clipping_name)
        curtailment_name = os.path.join(PV_REPORTS_PROJECT_PATH, "Reports", "pv_curtailment.json")
        curtailment = load_data(curtailment_name)

    total_cm_p1ulv53232_1_2_pv = 2233.5718
    total_cm_p1ulv57596_1_2_3_pv = 650.3959
    overall_total_cm = total_cm_p1ulv53232_1_2_pv + total_cm_p1ulv57596_1_2_3_pv
    total_pf1_p1ulv53232_1_2_pv = 2389.4002
    total_pf1_p1ulv57596_1_2_3_pv = 650.3996
    overall_total_pf1 = total_pf1_p1ulv53232_1_2_pv + total_pf1_p1ulv57596_1_2_3_pv
    if granularity == ReportGranularity.PER_ELEMENT_PER_TIME_POINT:
        df = s_cm.get_full_dataframe("PVSystems", "Powers")
        assert math.isclose(df["PVSystem.small_p1ulv53232_1_2_pv__Powers"].sum(), total_cm_p1ulv53232_1_2_pv, rel_tol=1e-04)
        assert math.isclose(df["PVSystem.small_p1ulv57596_1_2_3_pv__Powers"].sum(), total_cm_p1ulv57596_1_2_3_pv, rel_tol=1e-04)
        df = s_pf1.get_full_dataframe("PVSystems", "Powers")
        assert math.isclose(df["PVSystem.small_p1ulv53232_1_2_pv__Powers"].sum(), total_pf1_p1ulv53232_1_2_pv, rel_tol=1e-04)
        assert math.isclose(df["PVSystem.small_p1ulv57596_1_2_3_pv__Powers"].sum(), total_pf1_p1ulv57596_1_2_3_pv, rel_tol=1e-04)
    elif granularity == ReportGranularity.PER_ELEMENT_TOTAL:
        df = s_cm.get_full_dataframe("PVSystems", "PowersSum")
        assert math.isclose(df["PVSystem.small_p1ulv53232_1_2_pv__Powers"].values[0], total_cm_p1ulv53232_1_2_pv, rel_tol=1e-04)
        assert math.isclose(df["PVSystem.small_p1ulv57596_1_2_3_pv__Powers"].values[0], total_cm_p1ulv57596_1_2_3_pv, rel_tol=1e-04)
        df = s_pf1.get_full_dataframe("PVSystems", "PowersSum")
        assert math.isclose(df["PVSystem.small_p1ulv53232_1_2_pv__Powers"].values[0], total_pf1_p1ulv53232_1_2_pv, rel_tol=1e-04)
        assert math.isclose(df["PVSystem.small_p1ulv57596_1_2_3_pv__Powers"].values[0], total_pf1_p1ulv57596_1_2_3_pv, rel_tol=1e-04)
    elif granularity == ReportGranularity.ALL_ELEMENTS_TOTAL:
        assert math.isclose(s_cm.get_summed_element_total("PVSystems", "PowersSum")['Total__Powers'], overall_total_cm, rel_tol=1e-04)
        assert math.isclose(s_pf1.get_summed_element_total("PVSystems", "PowersSum")['Total__Powers'], overall_total_pf1, rel_tol=1e-04)
    elif granularity == ReportGranularity.ALL_ELEMENTS_PER_TIME_POINT:
        df = s_cm.get_summed_element_dataframe("PVSystems", "Powers")
        assert math.isclose(df["Total__Powers"].sum(), overall_total_cm, rel_tol=1e-04)
        df = s_pf1.get_summed_element_dataframe("PVSystems", "Powers")
        assert math.isclose(df["Total__Powers"].sum(), overall_total_pf1, rel_tol=1e-04)


def verify_thermal_metrics(baseline_metrics):
    filename = Path(PV_REPORTS_PROJECT_PATH) / "Reports" / "thermal_metrics.json"
    metrics = SimulationThermalMetricsModel(**load_data(filename))
    match = True
    for scenario in metrics.scenarios:
        if not compare_thermal_metrics(
            baseline_metrics.scenarios[scenario].line_loadings,
            metrics.scenarios[scenario].line_loadings,
        ):
            match = False

    return match


def verify_voltage_metrics(baseline_metrics):
    filename = Path(PV_REPORTS_PROJECT_PATH) / "Reports" / "voltage_metrics.json"
    metrics = SimulationVoltageMetricsModel(**load_data(filename))
    match = True
    for scenario in metrics.scenarios:
        if not compare_voltage_metrics(
            baseline_metrics.scenarios[scenario],
            metrics.scenarios[scenario],
        ):
            match = False

    return match


def verify_feeder_losses(baseline_metrics):
    filename = Path(PV_REPORTS_PROJECT_PATH) / "Reports" / "feeder_losses.json"
    metrics = SimulationFeederLossesMetricsModel(**load_data(filename))
    return compare_feeder_losses(baseline_metrics, metrics)


def verify_skip_night():
    results = PyDssResults(PV_REPORTS_PROJECT_PATH)
    scenario = results.scenarios[0]
    df = scenario.get_full_dataframe("PVSystems", "Powers")
    # Anytime before 6am or after 6pm should be excluded.
    # Some times in the middle of the day have convergence errors.
    for i in range(24):
        for val in df.iloc[i, :]:
            assert np.isnan(val)
    for i in range(24, 30):
        for val in df.iloc[i, :]:
            assert not np.isnan(val)
    for i in range(90, 96):
        for val in df.iloc[i, :]:
            assert np.isnan(val)


def verify_feeder_head_metrics():
    results = PyDssResults(PV_REPORTS_PROJECT_PATH)
    scenario = results.scenarios[0]
    df = scenario.get_full_dataframe("FeederHead", "load_kvar")
    assert len(df) == 96
    assert np.isnan(df.values[0])
    df = scenario.get_full_dataframe("FeederHead", "load_kw")
    assert len(df) == 96
    assert np.isnan(df.values[0])
    df = scenario.get_full_dataframe("FeederHead", "loading")
    assert len(df) == 96
    assert np.isnan(df.values[0])
    df = scenario.get_full_dataframe("FeederHead", "reverse_power_flow")
    assert len(df) == 96
    # TODO: figure out why this doesn't come back as NaN
    assert df.values[0] == -9999
