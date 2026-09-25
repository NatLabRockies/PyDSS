"""Creates reports on data exported by PyDSS"""

from datetime import timedelta
import time
import copy
import math
import abc
import os

from loguru import logger

from pydss.common import DataConversion, ReportGranularity
from pydss.exceptions import InvalidConfiguration
from pydss.simulation_input_models import SimulationSettingsModel
from pydss.utils.dataframe_utils import write_dataframe
from pydss.utils.simulation_utils import create_time_range_from_settings
from pydss.utils.utils import dump_data, make_json_serializable


REPORTS_DIR = "Reports"


class Reports:
    """Generate reports from a pydss project"""

    def __init__(self, results):
        self._results = results
        self._report_names = []
        self._settings = results.simulation_config
        for report in results.simulation_config.reports.types:
            if report.enabled:
                self._report_names.append(report.name)
        self._output_dir = os.path.join(results.project_path, REPORTS_DIR)
        os.makedirs(self._output_dir, exist_ok=True)

    @staticmethod
    def append_required_exports(exports, settings: SimulationSettingsModel):
        """Append export properties required by the configured reports.

        Parameters
        ----------
        exports : ExportListReader
        settings : SimulationSettingsModel

        """
        all_reports = Reports.get_all_reports()
        report_settings = settings.reports
        if not report_settings:
            return

        existing_scenarios = {x.name for x in settings.project.scenarios}
        for report in report_settings.types:
            if not report.enabled:
                continue
            name = report.name
            if name not in all_reports:
                raise InvalidConfiguration(f"{name} is not a valid report")

            required_scenarios = all_reports[name].get_required_scenario_names()
            missing = required_scenarios.difference(existing_scenarios)
            if missing:
                text = " ".join(missing)
                raise InvalidConfiguration(f"{name} requires these scenarios: {text}")

            scenarios = report.scenarios
            active_scenario = settings.project.active_scenario
            if scenarios and active_scenario not in scenarios:
                logger.debug("report %s is not enabled for scenario %s", name, active_scenario)
                continue

            required = all_reports[name].get_required_exports(settings)
            for elem_class, required_properties in required.items():
                for req_prop in required_properties:
                    found = False
                    store_type = req_prop.get("store_values_type", "all")
                    for prop in exports.list_element_properties(elem_class):
                        if (
                            prop.name == req_prop["property"]
                            and prop.store_values_type.value == store_type
                        ):
                            if prop.opendss_classes or req_prop.get("opendss_classes"):
                                assert prop.sum_elements == req_prop.get("sum_elements", False)
                                assert prop.data_conversion == req_prop.get(
                                    "data_conversion", DataConversion.NONE
                                )
                                prop.append_opendss_classes(req_prop["opendss_classes"])
                            found = True
                    if not found:
                        exports.append_property(elem_class, req_prop)
                        logger.debug("Add required property: %s %s", elem_class, req_prop)

            all_reports[name].set_required_project_settings(settings)

    @staticmethod
    def get_all_reports():
        reports = {}

        def append_reports(report_cls):
            subclasses = report_cls.__subclasses__()
            if subclasses:
                for cls in subclasses:
                    # Recurse.
                    append_reports(cls)
            else:
                reports[report_cls.NAME] = report_cls

        append_reports(ReportBase)
        return reports

    @classmethod
    def generate_reports(cls, results):
        """Generate all reports specified in the configuration.

        Parameters
        ----------
        results : PyDssResults

        Returns
        -------
        list
            list of report filenames

        """
        reports = Reports(results)
        return reports.generate()

    def generate(self):
        """Generate all reports specified in the configuration.

        Returns
        -------
        list
            list of report filenames

        """
        filenames = []
        all_reports = self.get_all_reports()
        for name in self._report_names:
            report = all_reports[name](name, self._results, self._settings)
            start = time.time()
            filename = report.generate(self._output_dir)
            duration = round(time.time() - start, 3)
            logger.info("Time to create %s report: %s seconds", name, duration)
            filenames.append(filename)

        return filenames


# Note to devs:  all subclasses of ReportBase need to reside in PyDSS/reports
# in order to be automatically imported. Otherwise, add a direct import in
# PyDSS/reports/__init__.py.


class ReportBase(abc.ABC):
    """Base class for reports"""

    def __init__(self, name, results, settings):
        self._results = results
        self._scenarios = results.scenarios
        self._settings = settings
        self._report_global_settings = settings.reports
        self._report_settings = _get_report_settings(settings, name)

    @abc.abstractmethod
    def generate(self, output_dir):
        """Generate a report in output_dir.

        Returns
        -------
        str
            path to report

        """

    @staticmethod
    @abc.abstractmethod
    def get_required_exports(simulation_config):
        """Return the properties required for the report for export.

        Parameters
        ----------
        simulation_config: dict
            settings from simulation config file

        Returns
        -------
        dict

        """

    @staticmethod
    @abc.abstractmethod
    def get_required_scenario_names():
        """Return the scenario names that the report expects to be able to retrieve.

        Returns
        -------
        set
            Set of strings

        """

    @staticmethod
    def get_inputs_from_defaults(settings: SimulationSettingsModel, name):
        all_reports = Reports.get_all_reports()
        report_settings = _get_report_settings(settings, name)
        inputs = copy.deepcopy(getattr(all_reports[name], "DEFAULTS"))
        for key in type(report_settings).model_fields:
            inputs[key] = getattr(report_settings, key)

        return inputs

    @staticmethod
    def set_required_project_settings(settings: SimulationSettingsModel):
        """Make report-required changes to the simulation config.

        Parameters
        ----------
        simulation_config : SimulationSettingsModel
            Settings to be modified.

        """
        # Default behavior is no change.

    def _export_dataframe_report(self, df, output_dir, basename):
        """Export report to a dataframe."""
        fmt = self._report_global_settings.format
        filename = os.path.join(output_dir, basename + "." + fmt.value)
        compress = True if fmt == "h5" else False
        write_dataframe(df, filename, compress=compress)
        logger.info("Generated %s", filename)
        return filename

    def _export_json_report(self, data, output_dir, filename):
        """Export report to a JSON file."""
        filename = os.path.join(output_dir, filename)
        dump_data(data, filename, indent=2, default=make_json_serializable)
        logger.info("Generated %s", filename)

    def _get_simulation_resolution(self):
        res = self._settings.project.step_resolution_sec
        return timedelta(seconds=res)

    def _get_num_steps(self):
        start, end, step = create_time_range_from_settings(self._settings)
        return math.ceil((end - start) / step)

    @staticmethod
    def _params_from_granularity(granularity):
        if granularity == ReportGranularity.PER_ELEMENT_PER_TIME_POINT:
            store_values_type = "all"
            sum_elements = False
        elif granularity == ReportGranularity.PER_ELEMENT_TOTAL:
            store_values_type = "sum"
            sum_elements = False
        elif granularity == ReportGranularity.ALL_ELEMENTS_PER_TIME_POINT:
            store_values_type = "all"
            sum_elements = True
        elif granularity == ReportGranularity.ALL_ELEMENTS_TOTAL:
            store_values_type = "sum"
            sum_elements = True
        else:
            assert False, str(granularity)

        return store_values_type, sum_elements


def _get_report_settings(settings: SimulationSettingsModel, name):
    for report in settings.reports.types:
        if report.name == name:
            return report

    assert False, f"{name} is not present"
