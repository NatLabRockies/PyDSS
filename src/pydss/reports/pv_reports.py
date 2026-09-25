import math
import abc
import os

from loguru import logger
import pandas as pd
import numpy as np

from pydss.common import PV_LOAD_SHAPE_FILENAME
from pydss.reports.reports import ReportBase, ReportGranularity
from pydss.utils.dataframe_utils import read_dataframe

PF1_SCENARIO = "pf1"
CONTROL_MODE_SCENARIO = "control_mode"


class PvReportBase(ReportBase, abc.ABC):
    """Base class for PV reports"""

    def __init__(self, name, results, simulation_config):
        super().__init__(name, results, simulation_config)
        assert len(results.scenarios) == 2
        self._control_mode_scenario = results.scenarios[0]
        assert self._control_mode_scenario.name == "control_mode"
        self._pf1_scenario = results.scenarios[1]
        cm_profiles = self._control_mode_scenario.read_pv_profiles()
        if not cm_profiles:
            self._pv_system_names = []
            return

        self._pv_system_names = [x["name"] for x in cm_profiles["pv_systems"]]

        self._pf1_pv_systems = {
            x["name"]: x for x in self._pf1_scenario.read_pv_profiles()["pv_systems"]
        }
        self._control_mode_pv_systems = {x["name"]: x for x in cm_profiles["pv_systems"]}

    def _get_pv_system_info(self, pv_system, scenario):
        if scenario == PF1_SCENARIO:
            pv_systems = self._pf1_pv_systems
        else:
            pv_systems = self._control_mode_pv_systems

        return pv_systems[pv_system]

    def _has_pv_systems(self):
        return len(self._pv_system_names) > 0

    @staticmethod
    def get_required_exports(settings):
        granularity = ReportGranularity(settings.reports.granularity)
        _type, sum_elements = ReportBase._params_from_granularity(granularity)
        return {
            "PVSystems": [
                {
                    "property": "Powers",
                    "store_values_type": _type,
                    "sum_elements": sum_elements,
                    "data_conversion": "sum_abs_real",
                },
            ],
        }

    @staticmethod
    def get_required_scenario_names():
        return set(["pf1", "control_mode"])

    @staticmethod
    def set_required_project_settings(settings):
        if not settings.exports.export_pv_profiles:
            settings.exports.export_pv_profiles = True
            logger.info("Enabled Export PV Profiles")


class PvClippingReport(PvReportBase):
    """Reports PV Clipping for the simulation.

    The report generates a pv_clipping output file. The file extension depends
    on the input parameters. If the data was collected at every time point then
    the output file will be .csv or .h5, depending on 'Export Format.'
    Otherwise, the output file will be .json.

    TODO: This is an experimental report. Outputs have not been validated.

    """

    PER_TIME_POINT_FILENAME = "pv_clipping.h5"
    TOTAL_FILENAME = "pv_clipping.json"
    NAME = "PV Clipping"

    def __init__(self, name, results, simulation_config):
        super().__init__(name, results, simulation_config)
        if not self._has_pv_systems():
            return

        diff_tolerance = self._report_settings.diff_tolerance_percent_pmpp * 0.01
        denominator_tolerance = self._report_settings.denominator_tolerance_percent_pmpp * 0.01
        logger.debug("tolerances: diff=%s denominator=%s", diff_tolerance, denominator_tolerance)
        self._diff_tolerances = {}
        self._denominator_tolerances = {}
        for pv_system in self._pf1_scenario.read_pv_profiles()["pv_systems"]:
            self._diff_tolerances[pv_system["name"]] = pv_system["pmpp"] * diff_tolerance
            self._denominator_tolerances[pv_system["name"]] = (
                pv_system["pmpp"] * denominator_tolerance
            )

    @staticmethod
    def _calculate_clipping(total_dc_power, pf1_real_power):
        return (total_dc_power - pf1_real_power) * 100 / pf1_real_power

    @staticmethod
    def _calculate_clipping_array(dc_power, pf1_real_power):
        dcp = dc_power.values
        rp = pf1_real_power.values
        rp = np.where(rp == 0, np.nan, rp)
        return (dcp - rp) / rp * 100

    def _get_total_dc_power_across_pv_systems(self):
        total_dc_power = 0.0
        for name in self._pv_system_names:
            total_dc_power += self._get_total_dc_power(name)
        return total_dc_power

    def _get_total_dc_power(self, pv_system):
        cm_info = self._get_pv_system_info(pv_system, CONTROL_MODE_SCENARIO)
        pmpp = cm_info["pmpp"]
        irradiance = cm_info["irradiance"]
        total_irradiance = cm_info["load_shape_pmult_sum"]
        return pmpp * irradiance * total_irradiance

    def _generate_per_pv_system_per_time_point(self, output_dir):
        pv_load_shapes = self._read_pv_load_shapes()
        pf1_real_power_full = self._pf1_scenario.get_full_dataframe("PVSystems", "Powers")
        name = None

        # TODO: Apply tolerances to other granularity options.
        def calc_clipping(dcp, rp):
            if dcp < self._denominator_tolerances[name]:
                return 0
            diff = dcp - rp
            if diff < 0 and abs(diff) < self._diff_tolerances[name]:
                return 0
            return (dcp - rp) / rp * 100

        data = {}
        for _name in self._pv_system_names:
            name = _name
            cm_info = self._get_pv_system_info(name, CONTROL_MODE_SCENARIO)
            pf1_real_power = pf1_real_power_full[name + "__Powers"]
            dc_power = (
                pv_load_shapes[cm_info["load_shape_profile"]]
                * cm_info["pmpp"]
                * cm_info["irradiance"]
            )
            assert len(dc_power) == len(pf1_real_power), f"{len(dc_power)} {len(pf1_real_power)}"
            col = name + "__Clipping"
            data[col] = dc_power.combine(pf1_real_power, calc_clipping).values

        df = pd.DataFrame(data, index=pf1_real_power_full.index)
        self._export_dataframe_report(df, output_dir, "pv_clipping")

    def _generate_per_pv_system_total(self, output_dir):
        data = {"pv_systems": []}
        for name in self._pv_system_names:
            pf1_real_power = self._pf1_scenario.get_element_property_value(
                "PVSystems", "PowersSum", name
            )
            dc_power = self._get_total_dc_power(name)
            clipping = self._calculate_clipping(dc_power, pf1_real_power)
            data["pv_systems"].append(
                {
                    "name": name,
                    "clipping": clipping,
                }
            )
        self._export_json_report(data, output_dir, self.TOTAL_FILENAME)

    def _generate_all_pv_systems_per_time_point(self, output_dir):
        pf1_real_power = self._pf1_scenario.get_summed_element_dataframe("PVSystems", "Powers")
        pv_load_shapes = self._read_pv_load_shapes()
        dc_powers = {}
        for name in self._pv_system_names:
            cm_info = self._get_pv_system_info(name, CONTROL_MODE_SCENARIO)
            series = pv_load_shapes[cm_info["load_shape_profile"]]
            dc_power = series * cm_info["pmpp"] * cm_info["irradiance"]
            assert len(dc_power) == len(pf1_real_power)
            dc_powers[name] = dc_power.values
            # TODO: just for validation
            assert math.isclose(
                sum(dc_power.values),
                cm_info["load_shape_pmult_sum"] * cm_info["pmpp"] * cm_info["irradiance"],
            )
        df = pd.DataFrame(dc_powers, index=pf1_real_power.index)
        total_dc_power = df.sum(axis=1)

        clipping = pd.DataFrame(
            self._calculate_clipping_array(total_dc_power, pf1_real_power.iloc[:, 0]),
            index=pf1_real_power.index,
            columns=["TotalClipping"],
        )
        self._export_dataframe_report(clipping, output_dir, "pv_clipping")

    def _generate_all_pv_systems_total(self, output_dir):
        total_dc_power = self._get_total_dc_power_across_pv_systems()

        pf1_real_power = next(
            iter(self._pf1_scenario.get_summed_element_total("PVSystems", "PowersSum").values())
        )
        clipping = self._calculate_clipping(total_dc_power, pf1_real_power)
        data = {"clipping": clipping}
        self._export_json_report(data, output_dir, self.TOTAL_FILENAME)

    def _read_pv_load_shapes(self):
        path = os.path.join(
            str(self._settings.project.active_project_path),
            "Exports",
            CONTROL_MODE_SCENARIO,
            PV_LOAD_SHAPE_FILENAME,
        )
        return read_dataframe(path)

    def generate(self, output_dir):
        if not self._has_pv_systems():
            return

        granularity = self._settings.reports.granularity
        if granularity == ReportGranularity.PER_ELEMENT_PER_TIME_POINT:
            self._generate_per_pv_system_per_time_point(output_dir)
        elif granularity == ReportGranularity.PER_ELEMENT_TOTAL:
            self._generate_per_pv_system_total(output_dir)
        elif granularity == ReportGranularity.ALL_ELEMENTS_PER_TIME_POINT:
            self._generate_all_pv_systems_per_time_point(output_dir)
        elif granularity == ReportGranularity.ALL_ELEMENTS_TOTAL:
            self._generate_all_pv_systems_total(output_dir)
        else:
            assert False


class PvCurtailmentReport(PvReportBase):
    """Reports PV Curtailment at every time point in the simulation.

    The report generates a pv_curtailment output file. The file extension
    depends on the input parameters. If the data was collected at every time
    point then the output file will be .csv or .h5, depending on 'Export
    Format.' Otherwise, the output file will be .json.

    TODO: This is an experimental report. Outputs have not been validated.

    """

    PER_TIME_POINT_FILENAME = "pv_curtailment.h5"
    TOTAL_FILENAME = "pv_curtailment.json"
    NAME = "PV Curtailment"

    def __init__(self, name, results, simulation_config):
        super().__init__(name, results, simulation_config)
        if not self._has_pv_systems():
            return

        diff_tolerance = self._report_settings.diff_tolerance_percent_pmpp * 0.01
        denominator_tolerance = self._report_settings.denominator_tolerance_percent_pmpp * 0.01
        logger.debug("tolerances: diff=%s denominator=%s", diff_tolerance, denominator_tolerance)
        self._diff_tolerances = {}
        self._denominator_tolerances = {}
        for pv_system in self._pf1_scenario.read_pv_profiles()["pv_systems"]:
            self._diff_tolerances[pv_system["name"]] = pv_system["pmpp"] * diff_tolerance
            self._denominator_tolerances[pv_system["name"]] = (
                pv_system["pmpp"] * denominator_tolerance
            )

    def _generate_per_pv_system_per_time_point(self, output_dir):
        pf1_power = self._pf1_scenario.get_full_dataframe("PVSystems", "Powers")
        control_mode_power = self._control_mode_scenario.get_full_dataframe("PVSystems", "Powers")
        name = None

        def calc_curtailment(pf1, cm):
            if pf1 < self._denominator_tolerances[name]:
                return 0
            diff = pf1 - cm
            if diff < 0 and abs(diff) < self._diff_tolerances[name]:
                return 0
            return (pf1 - cm) / pf1 * 100

        data = {}
        for col in pf1_power.columns:
            name = col.split("__")[0]
            s_pf1 = pf1_power[col]
            s_cm = control_mode_power[col]
            new_name = col.replace("Powers", "Curtailment")
            data[new_name] = s_pf1.combine(s_cm, calc_curtailment).values

        df = pd.DataFrame(data, index=pf1_power.index)
        self._export_dataframe_report(df, output_dir, "pv_curtailment")

    def _generate_per_pv_system_total(self, output_dir):
        data = {"pv_systems": []}
        for name in self._pv_system_names:
            pf1_power = self._pf1_scenario.get_element_property_value(
                "PVSystems", "PowersSum", name
            )
            control_mode_power = self._control_mode_scenario.get_element_property_value(
                "PVSystems", "PowersSum", name
            )
            curtailment = (pf1_power - control_mode_power) / pf1_power * 100
            data["pv_systems"].append(
                {
                    "name": name,
                    "curtailment": curtailment,
                }
            )
        self._export_json_report(data, output_dir, self.TOTAL_FILENAME)

    def _generate_all_pv_systems_per_time_point(self, output_dir):
        pf1_power = self._pf1_scenario.get_summed_element_dataframe("PVSystems", "Powers")
        control_mode_power = self._control_mode_scenario.get_summed_element_dataframe(
            "PVSystems", "Powers"
        )
        df = (pf1_power - control_mode_power) / pf1_power * 100
        self._export_dataframe_report(df, output_dir, "pv_curtailment")

    def _generate_all_pv_systems_total(self, output_dir):
        pf1_power = next(
            iter(self._pf1_scenario.get_summed_element_total("PVSystems", "PowersSum").values())
        )
        control_mode_power = next(
            iter(
                self._control_mode_scenario.get_summed_element_total(
                    "PVSystems", "PowersSum"
                ).values()
            )
        )

        curtailment = (pf1_power - control_mode_power) / pf1_power * 100
        data = {"curtailment": curtailment}
        self._export_json_report(data, output_dir, self.TOTAL_FILENAME)

    def generate(self, output_dir):
        if not self._has_pv_systems():
            return

        granularity = ReportGranularity(self._settings.reports.granularity)
        if granularity == ReportGranularity.PER_ELEMENT_PER_TIME_POINT:
            self._generate_per_pv_system_per_time_point(output_dir)
        elif granularity == ReportGranularity.PER_ELEMENT_TOTAL:
            self._generate_per_pv_system_total(output_dir)
        elif granularity == ReportGranularity.ALL_ELEMENTS_PER_TIME_POINT:
            self._generate_all_pv_systems_per_time_point(output_dir)
        elif granularity == ReportGranularity.ALL_ELEMENTS_TOTAL:
            self._generate_all_pv_systems_total(output_dir)
        else:
            assert False

    def calculate_pv_curtailment(self):
        """Calculate PV curtailment for all PV systems.

        Returns
        -------
        pd.DataFrame

        """
        pf1_power = self._pf1_scenario.get_full_dataframe("PVSystems", "Powers", real_only=True)
        control_mode_power = self._control_mode_scenario.get_full_dataframe(
            "PVSystems", "Powers", real_only=True
        )
        return (pf1_power - control_mode_power) / pf1_power * 100
