from typing import Dict, Union, Annotated, Optional
from collections import defaultdict
import math
import os

from loguru import logger
from pydantic import BaseModel, Field

from pydss.utils.simulation_utils import CircularBufferHelper
from pydss.utils.utils import dump_data, load_data
from pydantic import ConfigDict

class ThermalMetricsBaseModel(BaseModel):
    model_config = ConfigDict(title="ThermalMetricsBaseModel", str_strip_whitespace=True, validate_assignment=True, validate_default=True, extra="forbid", use_enum_values=False)


class ThermalMetricsModel(ThermalMetricsBaseModel):
    max_instantaneous_loadings_pct: Annotated[
        Dict[str, float],
        Field(
            {},
            title="max_instantaneous_loadings_pct",
            description="maximum instantaneous loading percent for each element",
        )]
    max_instantaneous_loading_pct: Annotated[
        float,
        Field(
            default = 120,
            title="max_instantaneous_loading_pct",
            description="maximum instantaneous loading percent overall",
        )]
    max_moving_average_loadings_pct: Annotated[
        Dict[str, float],
        Field(
            {},
            title="max_moving_average_loadings_pct",
            description="maximum moving average loading percent for each element",
        )]
    max_moving_average_loading_pct: Annotated[
        float,
        Field(
            100,
            title="max_moving_average_loading_pct",
            description="maximum moving average loading percent overall",
        )]
    window_size_hours: Annotated[
        Optional[int],
        Field(
            None,
            title="window_size_hours",
            description="window size used to calculate the moving average",
        )]
    num_time_points_with_instantaneous_violations: Annotated[
        Optional[int],
        Field(
            None,
            title="num_time_points_with_instantaneous_violations",
            description="number of time points where the instantaneous threshold was violated",
        )]
    num_time_points_with_moving_average_violations: Annotated[
        Optional[int],
        Field(
            None,
            title="num_time_points_with_moving_average_violations",
            description="number of time points where the moving average threshold was violated",
        )]
    instantaneous_threshold: Annotated[
        Optional[int],
        Field(
            None,
            title="instantaneous_threshold",
            description="instantaneous threshold",
        )]
    moving_average_threshold: Annotated[
        Optional[int],
        Field(
            None,
            title="moving_average_threshold",
            description="moving average threshold",
        )]


def compare_thermal_metrics(metrics1: ThermalMetricsModel, metrics2: ThermalMetricsModel, rel_tol=0.001):
    """Compares the values of two instances of ThermalMetricsModel.
    Uses a tolerance of 0.001 for moving averages.

    Returns
    -------
    bool
        Return True if they match.

    """
    match = True
    fields = (
        "max_instantaneous_loading_pct", "window_size_hours",
        "num_time_points_with_instantaneous_violations",
        "num_time_points_with_moving_average_violations",
        "instantaneous_threshold", "moving_average_threshold",
    )
    for field in fields:
        val1 = getattr(metrics1, field)
        val2 = getattr(metrics2, field)
        if val1 != val2:
            logger.error("field=%s mismatch %s != %s", field, val1, val2)
            match = False

    if not math.isclose(metrics1.max_moving_average_loading_pct, metrics2.max_moving_average_loading_pct, rel_tol=rel_tol):
        logger.error("max_moving_average_loading_pct mismatch %s != %s",
                     metrics1.max_moving_average_loading_pct, metrics2.max_instantaneous_loading_pct)
        match = False

    for name, val1 in metrics1.max_instantaneous_loadings_pct.items():
        val2 = metrics2.max_instantaneous_loadings_pct[name]
        if not math.isclose(val1, val2, rel_tol=rel_tol):
            logger.error("max_instantaneous_loadings_pct mismatch %s != %s", name, val1, val2)
            match = False

    for name, val1 in metrics1.max_moving_average_loadings_pct.items():
        val2 = metrics2.max_moving_average_loadings_pct[name]
        if not math.isclose(val1, val2, rel_tol=rel_tol):
            logger.error("max_moving_average_loadings_pct mismatch %s != %s", name, val1, val2)
            match = False

    return match


class ThermalMetricsSummaryModel(ThermalMetricsBaseModel):
    line_loadings: Annotated[
        ThermalMetricsModel,
        Field(
            title="line_loadings",
            description="line loading metrics",
        )]
    transformer_loadings: Annotated[
        Union[ThermalMetricsModel, None],
        Field(
            title="transformer_loadings",
            description="transformer loading metrics",
        )]


class SimulationThermalMetricsModel(ThermalMetricsBaseModel):
    scenarios: Annotated[
        Dict[str, ThermalMetricsSummaryModel],
        Field(
            title="scenarios",
            description="thermal metrics by pydss scenario name",
        )]


def create_summary(filename):
    data = load_data(filename)
    return create_summary_from_dict(data)


def create_summary_from_dict(data):
    """Create a summary of the metrics values for use in a table.

    Parameters
    ----------
    filename: str
        File containing a serialized SimulationThermalMetricsModel instance

    Returns
    -------
    dict
        Two-level dict. First level keys are scenario names. Second level has line/transform
        metric names and values.

    """
    summary = SimulationThermalMetricsModel(**data)
    report = defaultdict(dict)
    for scenario in summary.scenarios:
        for model, elem_type in zip(("line_loadings", "transformer_loadings"), ("line", "transformer")):
            model = getattr(summary.scenarios[scenario], model)
            if model is None:
                continue
            for column in model.model_fields:
                val = getattr(model, column)
                if not isinstance(val, dict):
                    new_name = elem_type + "_" + column
                    report[scenario][new_name] = val

    return report


class ThermalMetrics:
    """Stores thermal metrics in memory.

    The metrics are defined in this paper:
    https://www.sciencedirect.com/science/article/pii/S0306261920311351

    """

    FILENAME = "thermal_metrics.json"

    def __init__(
        self,
        prop,
        start_time,
        sim_resolution,
        line_window_size_hours,
        line_window_size,
        transformer_window_size_hours,
        transformer_window_size,
        line_loading_percent_threshold,
        line_loading_percent_moving_average_threshold,
        transformer_loading_percent_threshold,
        transformer_loading_percent_moving_average_threshold,
        store_per_element_data,
    ):
        self._prop = prop
        self._start_time = start_time
        self._resolution = sim_resolution
        self._line_window_size_hours = line_window_size_hours
        self._line_window_size = line_window_size
        self._line_loading_percent_threshold = line_loading_percent_threshold
        self._line_loading_percent_mavg_threshold = line_loading_percent_moving_average_threshold
        self._transformer_loading_percent_threshold = transformer_loading_percent_threshold
        self._transformer_window_size_hours = transformer_window_size_hours
        self._transformer_window_size = transformer_window_size
        self._transformer_loading_percent_mavg_threshold = transformer_loading_percent_moving_average_threshold
        self._num_time_points_inst_line_violations = 0
        self._num_time_points_mavg_line_violations = 0
        self._num_time_points_inst_transformer_violations = 0
        self._num_time_points_mavg_transformer_violations = 0
        self._max_inst_line_violations = None
        self._max_mavg_line_violations = None
        self._max_inst_transformer_violations = None
        self._max_mavg_transformer_violations = None
        self._line_bufs = None
        self._transformer_bufs = None
        self._num_time_points = 0
        self._line_names = None
        self._transformer_names = None
        self._store_per_element_data = store_per_element_data

    def generate_report(self, path):
        """Create a summary file containing all metrics.

        Parameters
        ----------
        path : str

        Returns
        -------
        str
            report filename

        """
        if self._num_time_points == 0 or self._max_inst_line_violations is None:
            logger.error("Cannot generate report with no data")
            return

        inst_violations_by_line = {}
        mavg_violations_by_line = {}
        for i in range(len(self._max_inst_line_violations)):
            inst_violations_by_line[self._line_names[i]] = self._max_inst_line_violations[i]
        for i in range(len(self._max_mavg_line_violations)):
            mavg_violations_by_line[self._line_names[i]] = self._max_mavg_line_violations[i]
        line_metric = ThermalMetricsModel(
            max_instantaneous_loadings_pct=inst_violations_by_line,
            max_instantaneous_loading_pct=max(inst_violations_by_line.values()),
            max_moving_average_loadings_pct=mavg_violations_by_line,
            max_moving_average_loading_pct=max(mavg_violations_by_line.values()),
            window_size_hours=self._line_window_size_hours,
            num_time_points_with_instantaneous_violations=self._num_time_points_inst_line_violations,
            num_time_points_with_moving_average_violations=self._num_time_points_mavg_line_violations,
            instantaneous_threshold=self._line_loading_percent_threshold,
            moving_average_threshold=self._line_loading_percent_mavg_threshold,
        )

        inst_violations_by_transformer = {}
        mavg_violations_by_transformer = {}
        for i in range(len(self._max_inst_transformer_violations)):
            inst_violations_by_transformer[self._transformer_names[i]] = self._max_inst_transformer_violations[i]
        for i in range(len(self._max_mavg_transformer_violations)):
            mavg_violations_by_transformer[self._transformer_names[i]] = self._max_mavg_transformer_violations[i]

        if self.has_transformers():
            transformer_metric = ThermalMetricsModel(
                max_instantaneous_loadings_pct=inst_violations_by_transformer,
                max_instantaneous_loading_pct=max(inst_violations_by_transformer.values()),
                max_moving_average_loadings_pct=mavg_violations_by_transformer,
                max_moving_average_loading_pct=max(mavg_violations_by_transformer.values()),
                window_size_hours=self._transformer_window_size_hours,
                num_time_points_with_instantaneous_violations=self._num_time_points_inst_transformer_violations,
                num_time_points_with_moving_average_violations=self._num_time_points_mavg_transformer_violations,
                instantaneous_threshold=self._transformer_loading_percent_threshold,
                moving_average_threshold=self._transformer_loading_percent_mavg_threshold,
            )
        else:
            transformer_metric = None

        if not self._store_per_element_data:
            line_metric.max_instantaneous_loadings_pct.clear()
            line_metric.max_moving_average_loadings_pct.clear()
            if self.has_transformers():
                transformer_metric.max_instantaneous_loadings_pct.clear()
                transformer_metric.max_moving_average_loadings_pct.clear()

        summary = ThermalMetricsSummaryModel(
            line_loadings=line_metric,
            transformer_loadings=transformer_metric,
        )

        filename = os.path.join(path, "thermal_metrics.json")
        with open(filename, "w") as f_out:
            f_out.write(summary.model_dump_json(indent=2))
            f_out.write("\n")
        logger.info("Generated thermal metric report in %s", filename)

    def has_transformers(self):
        return bool(self._transformer_names)

    @property
    def line_names(self):
        return self._line_names

    @property
    def transformer_names(self):
        return self._transformer_names

    @line_names.setter
    def line_names(self, names):
        self._line_names = names

    @transformer_names.setter
    def transformer_names(self, names):
        self._transformer_names = names

    def increment_steps(self):
        """Increment the time step counter."""
        self._num_time_points += 1

    def update(self, time_step, line_loadings, transformer_loadings):
        """Update the metrics for the time step.

        Parameters
        ----------
        time_step : int
        voltages : list
            list of ValueStorageBase

        """
        if self._line_bufs is None:
            self._line_bufs = [CircularBufferHelper(self._line_window_size) for _ in range(len(self._line_names))]
            self._transformer_bufs = [CircularBufferHelper(self._transformer_window_size) for _ in range(len(self._transformer_names))]
            self._max_inst_line_violations = [0.0] * len(self._line_names)
            self._max_mavg_line_violations = [0.0] * len(self._line_names)
            self._max_inst_transformer_violations = [0.0] * len(self._transformer_names)
            self._max_mavg_transformer_violations = [0.0] * len(self._transformer_names)

        has_inst_line_violation = False
        has_mavg_line_violation = False
        for i, loading in enumerate(line_loadings):
            if loading.value > self._max_inst_line_violations[i]:
                self._max_inst_line_violations[i] = loading.value
            if not has_inst_line_violation and loading.value > self._line_loading_percent_threshold:
                has_inst_line_violation = True

            buf = self._line_bufs[i]
            buf.append(loading.value)
            moving_avg = buf.average()

            if moving_avg > self._max_mavg_line_violations[i]:
                self._max_mavg_line_violations[i] = moving_avg
            if not has_mavg_line_violation and moving_avg > self._line_loading_percent_mavg_threshold:
                has_mavg_line_violation = True

        has_inst_transformer_violation = False
        has_mavg_transformer_violation = False
        for i, loading in enumerate(transformer_loadings):
            if loading.value > self._max_inst_transformer_violations[i]:
                self._max_inst_transformer_violations[i] = loading.value
            if not has_inst_transformer_violation and loading.value > self._transformer_loading_percent_threshold:
                has_inst_transformer_violation = True

            buf = self._transformer_bufs[i]
            buf.append(loading.value)
            moving_avg = buf.average()
            if moving_avg > self._max_mavg_transformer_violations[i]:
                self._max_mavg_transformer_violations[i] = moving_avg
            if not has_mavg_transformer_violation and moving_avg > self._transformer_loading_percent_mavg_threshold:
                has_mavg_transformer_violation = True

        if has_inst_line_violation:
            self._num_time_points_inst_line_violations += 1
        if has_mavg_line_violation:
            self._num_time_points_mavg_line_violations += 1
        if has_inst_transformer_violation:
            self._num_time_points_inst_transformer_violations += 1
        if has_mavg_transformer_violation:
            self._num_time_points_mavg_transformer_violations += 1
