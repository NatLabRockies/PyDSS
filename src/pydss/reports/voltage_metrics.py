from datetime import timedelta
import os

from loguru import logger
import numpy as np

from pydss.common import MinMax, NODE_NAMES_BY_TYPE_FILENAME
from pydss.reports.reports import ReportBase, ReportGranularity
from pydss.utils.utils import load_data
from pydss.node_voltage_metrics import (
    NodeVoltageMetricsByType,
    SimulationVoltageMetricsModel,
    VoltageMetricsByBusTypeModel,
    VoltageMetricsModel,
    VoltageMetric1,
    VoltageMetric2,
    VoltageMetric3,
    VoltageMetric4,
    VoltageMetric5,
    VoltageMetric6,
)


class VoltageMetrics(ReportBase):
    """Reports voltage metrics.

    The metrics are defined in this paper:
    https://www.sciencedirect.com/science/article/pii/S0306261920311351

    The report generates the output file Reports/voltage_metrics.json.
    Metrics 1, 2, 5, and 6 are included within that file.

    Metric 3 must be read from the raw data as in the example below.
    Metric 4 must be read from the dataframe-as-binary-file.

    This example assumes that data is stored on a per-time-point basis.

    .. code-block:: python

        from pydss.utils.dataframe_utils import read_dataframe
        from pydss.pydss_results import PyDssResults

        results = PyDssResults("path_to_project")
        control_mode_scenario = results.scenarios[1]

        # Read metrics 1, 2, 5, and 6 directly from JSON.
        voltage_metrics = results.read_report("Voltage Metrics")
        metric_4_filenames = voltage_metrics["metric_4"]
        dfs = [read_dataframe(x) for x in filenames]

        # Read all metric 3 dataframes from raw data into memory in one call.
        dfs = control_mode_scenario.get_filtered_dataframes("Nodes", "VoltageMetric")

        # Read metric 3 dataframes into memory one at a time.
        for node_name in control_mode_scenario.list_element_names("Nodes", "VoltageMetric"):
            df = control_mode_scenario.get_dataframe("Nodes", "VoltageMetric", node_name)
            # If necessary, convert to a moving average with pandas.

    """

    DEFAULTS = {
        "range_a_limits": [0.95, 1.05],
        "range_b_limits": [0.90, 1.0583],
        "window_size_minutes": 10,
        "store_all_time_points": False,
        "store_per_element_data": True,
    }
    FILENAME = "voltage_metrics.json"
    NAME = "Voltage Metrics"

    def __init__(self, name, results, simulation_config):
        super().__init__(name, results, simulation_config)
        self._granularity = ReportGranularity(self._report_global_settings.granularity)
        self._range_a_limits = MinMax(
            min=self._report_settings.range_a_limits[0],
            max=self._report_settings.range_a_limits[1],
        )
        self._range_b_limits = MinMax(
            min=self._report_settings.range_b_limits[0],
            max=self._report_settings.range_b_limits[1],
        )
        self._resolution = self._get_simulation_resolution()
        inputs = self.get_inputs_from_defaults(self._settings, self.NAME)
        self._window_size = timedelta(minutes=inputs["window_size_minutes"]) // self._resolution
        self._moving_window_minutes = inputs["window_size_minutes"]
        self._files_to_delete = []

    def generate(self, output_dir):
        inputs = VoltageMetrics.get_inputs_from_defaults(self._settings, self.NAME)
        if inputs["store_all_time_points"]:
            scenarios = self._generate_from_all_time_points()
        else:
            scenarios = self._generate_from_in_memory_metrics()
        model = SimulationVoltageMetricsModel(scenarios=scenarios)

        filename = os.path.join(output_dir, self.FILENAME)
        with open(filename, "w") as f_out:
            f_out.write(model.model_dump_json(indent=2))
            f_out.write("\n")

        logger.info("Generated %s", filename)
        for filename in self._files_to_delete:
            os.remove(filename)

    def _generate_from_in_memory_metrics(self):
        scenarios = {}
        for scenario in self._results.scenarios:
            filename = os.path.join(
                str(self._settings.project.active_project_path),
                "Exports",
                scenario.name,
                self.FILENAME,
            )
            scenarios[scenario.name] = VoltageMetricsByBusTypeModel(**load_data(filename))
            # We won't need this file after we write the consolidated file.
            self._files_to_delete.append(filename)

        return scenarios

    def _generate_from_all_time_points(self):
        scenarios = {}
        for scenario in self._results.scenarios:
            filename = os.path.join(
                str(self._settings.project.active_project_path),
                "Exports",
                scenario.name,
                NODE_NAMES_BY_TYPE_FILENAME,
            )
            node_names_by_type = load_data(filename)
            assert len(set(node_names_by_type["primaries"])) == len(node_names_by_type["primaries"])
            assert len(set(node_names_by_type["secondaries"])) == len(
                node_names_by_type["secondaries"]
            )
            df = scenario.get_full_dataframe("Buses", "puVmagAngle", mag_ang="mag")
            columns = []
            for column in df.columns:
                # Make the names match the results from NodeVoltageMetrics.
                column = column.replace("__mag [pu]", "")
                column = column.replace("__A1", ".1")
                column = column.replace("__B1", ".2")
                column = column.replace("__C1", ".3")
                columns.append(column)
            df.columns = columns

            by_type = {}
            for node_type in ("primaries", "secondaries"):
                df_by_type = df[node_names_by_type[node_type]]
                by_type[node_type] = self._gen_metrics(df_by_type)
            scenarios[scenario.name] = VoltageMetricsByBusTypeModel(**by_type)

        return scenarios

    def _gen_metrics(self, df):
        assert len(df) > 0
        metric_2 = {x: 0 for x in df.columns}
        metric_4 = []
        metric_5_min = {x: None for x in df.columns}
        metric_5_max = {x: None for x in df.columns}
        metric_1_violation_time_points = []
        num_time_points_violate_range_b = 0
        for timestamp, row in df.iterrows():
            num_range_a_violations = 0
            for name, val in row.items():
                if val > self._range_a_limits.max or val < self._range_a_limits.min:
                    metric_2[name] += 1
                    num_range_a_violations += 1
                cur_min = metric_5_min[name]
                cur_max = metric_5_max[name]
                if not np.isnan(val):
                    if cur_min is None or val < cur_min:
                        metric_5_min[name] = val
                    if cur_max is None or val > cur_max:
                        metric_5_max[name] = val
            max_val = row.max()
            min_val = row.min()
            if (
                not (max_val > self._range_b_limits.max)
                and not (min_val < self._range_b_limits.min)
                and (max_val > self._range_a_limits.max or min_val < self._range_a_limits.min)
            ):
                metric_1_violation_time_points.append(timestamp)
            if max_val > self._range_b_limits.max or min_val < self._range_b_limits.min:
                num_time_points_violate_range_b += 1

            if num_range_a_violations > 0:
                metric_4.append([timestamp, num_range_a_violations / len(df.columns) * 100])

        df_mavg = df.rolling(window=self._window_size).mean()
        metric_3 = []
        for timestamp, row in df_mavg.iterrows():
            max_val = row.max()
            min_val = row.min()
            if max_val > self._range_a_limits.max or min_val < self._range_a_limits.min:
                metric_3.append(timestamp)

        vmetric_1 = VoltageMetric1(
            time_points=metric_1_violation_time_points,
            duration=len(metric_1_violation_time_points) * self._resolution,
        )
        vmetric_2 = {
            name: VoltageMetric2(
                duration=val * self._resolution,
                duration_percentage=val / len(df) * 100,
            )
            for name, val in metric_2.items()
        }
        vmetric_3 = VoltageMetric3(
            time_points=metric_3,
            duration=len(metric_3) * self._resolution,
        )
        vmetric_4 = VoltageMetric4(
            percent_node_ansi_a_violations=metric_4,
        )
        vmetric_5 = VoltageMetric5(
            min_voltages=metric_5_min,
            max_voltages=metric_5_max,
        )
        vmetric_6 = VoltageMetric6(
            num_time_points=num_time_points_violate_range_b,
            percent_time_points=num_time_points_violate_range_b / len(df) * 100,
            duration=num_time_points_violate_range_b * self._resolution,
        )

        return VoltageMetricsModel(
            metric_1=vmetric_1,
            metric_2=vmetric_2,
            metric_3=vmetric_3,
            metric_4=vmetric_4,
            metric_5=vmetric_5,
            metric_6=vmetric_6,
            summary=NodeVoltageMetricsByType.create_summary(
                vmetric_1,
                vmetric_2,
                vmetric_3,
                vmetric_5,
                vmetric_6,
                list(df.columns),
                len(df),
                self._resolution,
                self._range_a_limits,
                self._range_b_limits,
                self._moving_window_minutes,
            ),
        )

    @staticmethod
    def get_required_exports(simulation_config):
        inputs = VoltageMetrics.get_inputs_from_defaults(simulation_config, VoltageMetrics.NAME)
        if inputs["store_all_time_points"]:
            return {
                # TODO: This should use Circuit.AllBusMagPu for performance reasons.
                # That reads all voltages in one command but tracks them by bus index.
                # The code would have to map bus index to bus name.
                "Buses": [
                    {
                        "property": "puVmagAngle",
                        "store_values_type": "all",
                    }
                ]
            }

        return {
            "Nodes": [
                {
                    "property": "VoltageMetric",
                    "store_values_type": "all",
                    "limits": inputs["range_a_limits"],
                    "limits_b": inputs["range_b_limits"],
                },
            ]
        }

    @staticmethod
    def get_required_scenario_names():
        return set()

    @staticmethod
    def set_required_project_settings(settings):
        inputs = VoltageMetrics.get_inputs_from_defaults(settings, VoltageMetrics.NAME)
        exports = settings.exports
        if inputs["store_all_time_points"] and not exports.export_node_names_by_type:
            exports.export_node_names_by_type = True
            logger.info("Enabled Export Node Names By Type")
