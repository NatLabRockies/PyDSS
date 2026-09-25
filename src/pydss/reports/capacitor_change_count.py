import os

from loguru import logger

from pydss.reports.reports import ReportBase
from pydss.utils.utils import dump_data


class CapacitorStateChangeReport(ReportBase):
    """Reports the state changes per Capacitor.

    The report generates a capacitor_state_changes.json output file.

    TODO: This is an experimental report. Outputs have not been validated.

    """

    FILENAME = "capacitor_state_changes.json"
    NAME = "Capacitor State Change Counts"

    def generate(self, output_dir):
        data = {"scenarios": []}
        for scenario in self._results.scenarios:
            scenario_data = {"name": scenario.name, "capacitors": []}
            for capacitor in scenario.list_element_names("Capacitors"):
                change_count = int(
                    scenario.get_element_property_value(
                        "Capacitors", "TrackStateChanges", capacitor
                    )
                )
                changes = {"name": capacitor, "change_count": change_count}
                scenario_data["capacitors"].append(changes)
            data["scenarios"].append(scenario_data)

        filename = os.path.join(output_dir, self.FILENAME)
        dump_data(data, filename, indent=2)
        logger.info("Generated %s", filename)
        return filename

    @staticmethod
    def get_required_exports(simulation_config):
        return {
            "Capacitors": [
                {
                    "property": "TrackStateChanges",
                    "store_values_type": "change_count",
                }
            ]
        }

    @staticmethod
    def get_required_scenario_names():
        return set()
