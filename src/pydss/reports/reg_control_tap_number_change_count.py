import os

from loguru import logger

from pydss.reports.reports import ReportBase
from pydss.utils.utils import dump_data


class RegControlTapNumberChangeReport(ReportBase):
    """Reports the tap number changes per RegControl.

    TODO: This is an experimental report. Outputs have not been validated.

    """

    FILENAME = "reg_control_tap_value_changes.json"
    NAME = "RegControl Tap Number Change Counts"

    def generate(self, output_dir):
        data = {"scenarios": []}
        for scenario in self._results.scenarios:
            scenario_data = {"name": scenario.name, "reg_controls": []}
            for reg_control in scenario.list_element_names("RegControls"):
                change_count = int(
                    scenario.get_element_property_value(
                        "RegControls", "TrackTapNumberChanges", reg_control
                    )
                )
                changes = {"name": reg_control, "change_count": change_count}
                scenario_data["reg_controls"].append(changes)
            data["scenarios"].append(scenario_data)

        filename = os.path.join(output_dir, self.FILENAME)
        dump_data(data, filename, indent=2)
        logger.info("Generated %s", filename)
        return filename

    @staticmethod
    def get_required_exports(simulation_config):
        return {
            "RegControls": [
                {
                    "property": "TrackTapNumberChanges",
                    "store_values_type": "change_count",
                }
            ]
        }

    @staticmethod
    def get_required_scenario_names():
        return set()
