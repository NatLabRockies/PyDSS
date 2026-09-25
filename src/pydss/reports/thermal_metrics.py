from datetime import timedelta
import os

from loguru import logger

from pydss.exceptions import InvalidConfiguration
from pydss.reports.reports import ReportBase
from pydss.thermal_metrics import (
    SimulationThermalMetricsModel,
    ThermalMetricsSummaryModel,
    ThermalMetricsModel,
)
from pydss.utils.utils import load_data


class ThermalMetrics(ReportBase):
    """Reports thermal metrics.

    The metrics are defined in this paper:
    https://www.sciencedirect.com/science/article/pii/S0306261920311351

    The report generates the output file Reports/thermal_metrics.json.

    """

    DEFAULTS = {
        "line_window_size_hours": 1,
        "line_loading_percent_threshold": 120,
        "line_loading_percent_moving_average_threshold": 100,
        "transformer_loading_percent_threshold": 150,
        "transformer_window_size_hours": 2,
        "transformer_loading_percent_moving_average_threshold": 120,
        "store_all_time_points": False,
        "store_per_element_data": True,
    }
    FILENAME = "thermal_metrics.json"
    NAME = "Thermal Metrics"

    def __init__(self, name, results, simulation_config):
        super().__init__(name, results, simulation_config)
        self._num_lines = 0
        self._num_transformers = 0
        self._resolution = self._get_simulation_resolution()
        self._files_to_delete = []

    def generate(self, output_dir):
        inputs = ThermalMetrics.get_inputs_from_defaults(self._settings, self.NAME)
        if inputs["store_all_time_points"]:
            scenarios = self._generate_from_all_time_points()
        else:
            scenarios = self._generate_from_in_memory_metrics()

        model = SimulationThermalMetricsModel(scenarios=scenarios)
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
            scenarios[scenario.name] = ThermalMetricsSummaryModel(**load_data(filename))
            # We won't need this file after we write the consolidated file.
            self._files_to_delete.append(filename)

        return scenarios

    def _generate_from_all_time_points(self):
        inputs = self.get_inputs_from_defaults(self._settings, self.NAME)
        line_window_size, transformer_window_size = self._get_window_sizes(inputs, self._resolution)
        scenarios = {}
        for scenario in self._results.scenarios:
            df = scenario.get_full_dataframe("CktElement", "ExportLoadingsMetric")
            # Remove the property label, like "__Loading" from the column.
            df.columns = [x.split("__")[0] for x in df.columns]
            line_columns = []
            transform_columns = []
            for col in df.columns:
                if col.startswith("Line"):
                    line_columns.append(col)
                elif col.startswith("Transformer"):
                    transform_columns.append(col)
            df_lines = df[line_columns]
            lines_model = self._make_thermal_metrics_model(
                df_lines,
                line_window_size,
                inputs["line_window_size_hours"],
                inputs["line_loading_percent_threshold"],
                inputs["line_loading_percent_moving_average_threshold"],
            )
            df_transformers = df[transform_columns]
            transformers_model = self._make_thermal_metrics_model(
                df_transformers,
                transformer_window_size,
                inputs["transformer_window_size_hours"],
                inputs["transformer_loading_percent_threshold"],
                inputs["transformer_loading_percent_moving_average_threshold"],
            )
            scenarios[scenario.name] = ThermalMetricsSummaryModel(
                line_loadings=lines_model,
                transformer_loadings=transformers_model,
            )

        return scenarios

    def _make_thermal_metrics_model(
        self, df, window_size, window_size_hours, inst_threshold, mavg_threshold
    ):
        df_mavg = df.rolling(window=window_size).mean()
        max_instantaneous = self._get_max_values(df)
        max_mavg = self._get_max_values(df_mavg)
        return ThermalMetricsModel(
            max_instantaneous_loadings_pct=max_instantaneous,
            max_instantaneous_loading_pct=max(max_instantaneous.values()),
            max_moving_average_loadings_pct=max_mavg,
            max_moving_average_loading_pct=max(max_mavg.values()),
            window_size_hours=window_size_hours,
            num_time_points_with_instantaneous_violations=self._get_num_time_points_with_violations(
                df, inst_threshold
            ),
            num_time_points_with_moving_average_violations=self._get_num_time_points_with_violations(
                df_mavg, mavg_threshold
            ),
            instantaneous_threshold=inst_threshold,
            moving_average_threshold=mavg_threshold,
        )

    @staticmethod
    def _get_window_sizes(inputs, resolution):
        line_window_size = timedelta(hours=inputs["line_window_size_hours"])
        if line_window_size % resolution != timedelta(0):
            raise InvalidConfiguration(
                f"line_window_size={line_window_size} must be a multiple of {resolution}"
            )
        transformer_window_size = timedelta(hours=inputs["transformer_window_size_hours"])
        if transformer_window_size % resolution != timedelta(0):
            raise InvalidConfiguration(
                f"transformer_window_size={transformer_window_size} must be a multiple of {resolution}"
            )
        return line_window_size // resolution, transformer_window_size // resolution

    @staticmethod
    def _get_max_values(df):
        """Return a dict with max values per column."""
        return {x: df[x].max() for x in df.columns}

    @staticmethod
    def _get_num_time_points_with_violations(df, threshold):
        """Return the number of time points where at least one value exceeds threshold."""
        num_violations = 0
        for i, row in df.iterrows():
            if row.max() > threshold:
                num_violations += 1

        return num_violations

    @staticmethod
    def get_required_exports(simulation_config):
        inputs = ThermalMetrics.get_inputs_from_defaults(simulation_config, ThermalMetrics.NAME)
        if inputs["store_all_time_points"]:
            return {
                "CktElement": [
                    {
                        "property": "ExportLoadingsMetric",
                        "store_values_type": "all",
                        "opendss_classes": ["Lines", "Transformers"],
                    }
                ]
            }

        return {
            "CktElement": [
                {
                    "property": "OverloadsMetricInMemory",
                    "opendss_classes": ["Lines", "Transformers"],
                }
            ]
        }

    @staticmethod
    def get_required_scenario_names():
        return set()
