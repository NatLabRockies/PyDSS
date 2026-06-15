from typing import Dict, List, Union, Annotated
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, Field
from pydantic import ConfigDict

from pydss.utils.simulation_utils import CircularBufferHelper

class VoltageMetricsBaseModel(BaseModel):
    model_config = ConfigDict(title="VoltageMetricsBaseModel", str_strip_whitespace=True, validate_assignment=True, validate_default=True, extra="forbid", use_enum_values=False)


class VoltageMetric1(VoltageMetricsBaseModel):
    time_points: Annotated[
        List[datetime],
        Field(
            None,
            title="time_points",
            description="time points that contain voltages between ANSI A and ANSI B thresholds",
        )]
    duration: Annotated[
        timedelta,
        Field(
            None,
            title="duration",
            description="amount of time where metric 1 existed (len(time_points) * resolution)",
        )]


class VoltageMetric2(VoltageMetricsBaseModel):
    duration: Annotated[
        timedelta,
        Field(
            title="duration",
            description="amount of time where a node experienced ANSI A violations",
        )]
    duration_percentage: Annotated[
        float,
        Field(
            title="duration_percentage",
            description="percentage of overall time",
        )]


class VoltageMetric3(VoltageMetricsBaseModel):
    time_points: Annotated[
        List[datetime],
        Field(
            title="time_points",
            description="time points where moving average voltages violated ANSI A thresholds",
        )]
    duration:Annotated[
        timedelta,
        Field(
            title="duration",
            description="amount of time where metric 3 existed (len(time_points) * resolution)",
        )]


class VoltageMetric4(VoltageMetricsBaseModel):
    percent_node_ansi_a_violations: Annotated[
        List[List],
        Field(
            title="percent_node_ansi_a_violations",
            description="percent of nodes with ANSI A violations at time points. Excludes time "
            "points with no violations. Inner list is [timestamp, percent].",
        )]


class VoltageMetric5(VoltageMetricsBaseModel):
    min_voltages: Annotated[
        Dict,
        Field(
            title="min_voltage_by_node",
            description="Mapping of node name to minimum voltage",
        )]
    max_voltages: Annotated[
        Dict,
        Field(
            title="max_voltage_by_node",
            description="Mapping of node name to maximum voltage",
        )]


class VoltageMetric6(VoltageMetricsBaseModel):
    num_time_points: Annotated[
        int,
        Field(
            title="num_time_points",
            description="number of time points that violate ANSI B thresholds",
        )]
    percent_time_points: Annotated[
        float,
        Field(
            title="percent_time_points",
            description="percentage of time points that violate ANSI B thresholds",
        )]
    duration: Annotated[
        timedelta,
        Field(
            title="duration",
            description="amount of time where metric 6 existed (len(num_time_points) * resolution)",
        )]


class VoltageMetricsSummaryModel(VoltageMetricsBaseModel):
    voltage_duration_between_ansi_a_and_b_minutes: Annotated[
        int,
        Field(
            title="voltage_duration_between_ansi_a_and_b_minutes",
            description="time in minutes that contain voltages between ANSI A and ANSI B thresholds",
        )]
    max_per_node_voltage_duration_outside_ansi_a_minutes: Annotated[
        float,
            Field(
            title="max_per_node_voltage_duration_outside_ansi_a_minutes",
            description="maximum time in minutes that a node was outside ANSI A thresholds",
        )]
    moving_average_voltage_duration_outside_ansi_a_minutes: Annotated[
        float,
        Field(
            title="moving_average_voltage_duration_outside_ansi_a_minutes",
            description="time in minutes the moving average voltage was outside ANSI A",
        )]
    moving_window_minutes: Annotated[
        int,
        Field(
            title="moving_window_minutes",
            description="window size in minutes for moving average metrics",
        )]
    max_voltage: Annotated[
        float,
        Field(
            title="max_voltage",
            description="maximum voltage seen on any node",
        )]
    min_voltage: Annotated[
        float,
        Field(
            title="min_voltage",
            description="minimum voltage seen on any node",
        )]
    num_nodes_always_inside_ansi_a: Annotated[
        int,
            Field(
            title="num_nodes_always_inside_ansi_a",
            description="number of nodes always inside ANSI A thresholds",
        )]
    num_nodes_any_outside_ansi_a_always_inside_ansi_b: Annotated[
        int,
        Field(
            title="num_nodes_any_outside_ansi_a_always_inside_ansi_b",
            description="number of nodes with some ANSI A violations but no ANSI B violations",
        )]
    num_nodes_any_outside_ansi_b: Annotated[
        int,
        Field(
            title="num_nodes_always_outside_ansi_b",
            description="number of nodes with some ANSI B violations",
        )]
    num_time_points_with_ansi_b_violations: Annotated[
        int,
        Field(
            title="num_time_points_with_ansi_b_violations",
            description="number of time points with ANSI B violations",
        )]
    total_num_time_points: Annotated[
        int,
        Field(
            title="total_num_time_points",
            description="number of time points in the simulation",
        )]
    total_simulation_duration: Annotated[
        timedelta,
        Field(
            title="total_simulation_duration",
            description="total length of time of the simulation",
        )]


VOLTAGE_METRIC_FIELDS_TO_INCLUDE_AS_PASS_CRITERIA = (
    "voltage_duration_between_ansi_a_and_b_minutes",
    "max_per_node_voltage_duration_outside_ansi_a_minutes",
    "moving_average_voltage_duration_outside_ansi_a_minutes",
    "num_nodes_always_inside_ansi_a",
    "num_nodes_any_outside_ansi_a_always_inside_ansi_b",
    "num_nodes_any_outside_ansi_b",
    "num_time_points_with_ansi_b_violations",
    "min_voltage",
    "max_voltage",
)


class VoltageMetricsModel(VoltageMetricsBaseModel):
    metric_1: Annotated[
        VoltageMetric1,
        Field(
            title="metric_1",
            description="metric 1",
        )]
    metric_2: Annotated[
        Dict[str, VoltageMetric2],
        Field(
            title="metric_2",
            description="metric 2",
        )]
    metric_3: Annotated[
        VoltageMetric3,
        Field(
            title="metric_3",
            description="metric 3",
        )]
    metric_4: Annotated[
        VoltageMetric4,
        Field(
            title="metric_4",
            description="metric 4",
        )]
    metric_5: Annotated[
        VoltageMetric5,
        Field(
            title="metric_5",
            description="metric 5",
        )]
    metric_6: Annotated[
        VoltageMetric6,
        Field(
            title="metric_6",
            description="metric 6",
        )]
    summary: Annotated[
        Union[VoltageMetricsSummaryModel, None],
        Field(
            title="summary",
            description="summary of metrics",
        )]


class VoltageMetricsByBusTypeModel(VoltageMetricsBaseModel):
    """Metrics separated by bus type"""
    primaries: Annotated[
        VoltageMetricsModel,
        Field(
            title="primaries",
            description="metrics for primary buses",
        )]
    secondaries: Annotated[
        Union[VoltageMetricsModel, None],
        Field(
            title="secondaries",
            description="metrics for secondary buses",
            default=None,
        )]


class SimulationVoltageMetricsModel(VoltageMetricsBaseModel):
    scenarios: Annotated[
        Dict[str, VoltageMetricsByBusTypeModel],
        Field(
            title="scenarios",
            description="voltage metrics by pydss scenario name",
        )]


def compare_voltage_metrics(metrics1: VoltageMetricsByBusTypeModel, metrics2: VoltageMetricsByBusTypeModel):
    """Compares the values of two instances of VoltageMetricsModel.

    Returns
    -------
    bool
        Return True if they match.

    """
    match = True
    fields = (
        "voltage_duration_between_ansi_a_and_b_minutes",
        "max_per_node_voltage_duration_outside_ansi_a_minutes",
        "moving_average_voltage_duration_outside_ansi_a_minutes",
        "moving_window_minutes",
        "max_voltage",
        "min_voltage",
        "num_nodes_always_inside_ansi_a",
        "num_nodes_any_outside_ansi_a_always_inside_ansi_b",
        "num_nodes_any_outside_ansi_b",
        "num_time_points_with_ansi_b_violations",
        "total_num_time_points",
        "total_simulation_duration",
    )
    for node_type in ("primaries", "secondaries"):
        _metrics1 = getattr(metrics1, node_type)
        _metrics2 = getattr(metrics2, node_type)
        for field in fields:
            val1 = getattr(_metrics1.summary, field)
            val2 = getattr(_metrics2.summary, field)
            if val1 != val2:
                logger.error("field=%s mismatch %s != %s", field, val1, val2)
                match = False

        for field in ("metric_1", "metric_2", "metric_3", "metric_4", "metric_5", "metric_6"):
            val1 = getattr(_metrics1, field)
            val2 = getattr(_metrics2, field)
            if val1 != val2:
                logger.error("%s mismatch: val1=%s val2=%s", field, val1, val2)
                match = False

    return match


class NodeVoltageMetricsByType:
    def __init__(self, prop, start_time, resolution, window_size):
        self._start_time = start_time
        self._resolution = resolution
        self._range_a_limits = prop.limits
        self._range_b_limits = prop.limits_b
        self._window_size = window_size
        self._node_names = None
        self._node_indices = None
        self._metric_1_time_steps = []
        self._metric_2_violation_counts = []
        self._metric_3_time_steps = []
        self._metric_4_violations = []
        self._metric_5_min_violations = []
        self._metric_5_max_violations = []
        self._num_metric_6_time_points_outside_range_b = 0
        self._bufs = None
        self._num_time_points = 0

    @staticmethod
    def create_summary(metric_1, metric_2, metric_3, metric_5, metric_6, node_names,
                       num_time_points, resolution, range_a_limits, range_b_limits,
                       moving_window_minutes):
        if not node_names:
            # There may not be any secondary nodes.
            return None

        max_pnvdoaa = max((x.duration for x in metric_2.values())).total_seconds()
        vdbaab = metric_1.duration.total_seconds()
        mmavdoa = metric_3.duration.total_seconds()
        max_voltage_overall = max(metric_5.max_voltages.values())
        min_voltage_overall = min(metric_5.min_voltages.values())

        num_nodes_always_inside_range_a = 0
        num_nodes_any_outside_range_a_no_b = 0
        num_nodes_any_outside_range_b = 0
        for node in node_names:
            min_voltage = metric_5.min_voltages[node]
            max_voltage = metric_5.max_voltages[node]
            if (
                min_voltage < range_b_limits.min
                or max_voltage > range_b_limits.max
            ):
                num_nodes_any_outside_range_b += 1
            elif (
                min_voltage < range_a_limits.min
                or max_voltage > range_a_limits.max
            ):
                num_nodes_any_outside_range_a_no_b += 1
            else:
                num_nodes_always_inside_range_a += 1

        return VoltageMetricsSummaryModel(
            voltage_duration_between_ansi_a_and_b_minutes=vdbaab / 60,
            max_per_node_voltage_duration_outside_ansi_a_minutes=max_pnvdoaa / 60,
            moving_average_voltage_duration_outside_ansi_a_minutes=mmavdoa / 60,
            moving_window_minutes=moving_window_minutes,
            max_voltage=max_voltage_overall,
            min_voltage=min_voltage_overall,
            num_nodes_always_inside_ansi_a=num_nodes_always_inside_range_a,
            num_nodes_any_outside_ansi_a_always_inside_ansi_b=num_nodes_any_outside_range_a_no_b,
            num_nodes_any_outside_ansi_b=num_nodes_any_outside_range_b,
            num_time_points_with_ansi_b_violations=metric_6.num_time_points,
            total_num_time_points=num_time_points,
            total_simulation_duration=num_time_points * resolution,
        )

    def generate(self, store_per_element_data):
        if self._num_time_points == 0:
            logger.error("Cannot generate report with no time points")
            return

        metric_1 = VoltageMetric1(
            time_points=self._metric_1_time_steps,
            duration=len(self._metric_1_time_steps) * self._resolution,
        )
        metric_2 = {
            self._node_names[i]: VoltageMetric2(
                duration=x * self._resolution,
                duration_percentage=x / self._num_time_points * 100,
            )
            for i, x in enumerate(self._metric_2_violation_counts)
        }
        metric_3 = VoltageMetric3(
            time_points=self._metric_3_time_steps,
            duration=len(self._metric_3_time_steps) * self._resolution,
        )
        metric_4 = VoltageMetric4(
            percent_node_ansi_a_violations=self._metric_4_violations,
        )
        metric_5 = VoltageMetric5(
            min_voltages={
                self._node_names[i]: x
                for i, x in enumerate(self._metric_5_min_violations)
            },
            max_voltages={
                self._node_names[i]: x
                for i, x in enumerate(self._metric_5_max_violations)
            },
        )
        metric_6 = VoltageMetric6(
            num_time_points=self._num_metric_6_time_points_outside_range_b,
            percent_time_points=self._num_metric_6_time_points_outside_range_b
                / self._num_time_points
                * 100,
            duration=self._num_metric_6_time_points_outside_range_b * self._resolution,
        )
        moving_window_minutes = int(
            (self._window_size * self._resolution).total_seconds() / 60
        )

        metrics = VoltageMetricsModel(
            metric_1=metric_1,
            metric_2=metric_2,
            metric_3=metric_3,
            metric_4=metric_4,
            metric_5=metric_5,
            metric_6=metric_6,
            summary=self.create_summary(
                metric_1, metric_2, metric_3, metric_5, metric_6, self._node_names,
                self._num_time_points, self._resolution, self._range_a_limits, self._range_b_limits,
                moving_window_minutes,
            )
        )

        if not store_per_element_data:
            metrics.metric_1.time_points.clear()
            metrics.metric_2.clear()
            metrics.metric_3.time_points.clear()
            metrics.metric_4.percent_node_ansi_a_violations.clear()
            metrics.metric_5.min_voltages.clear()
            metrics.metric_5.max_voltages.clear()

        return metrics

    def has_data(self):
        return self._bufs is not None

    def update(self, time_step, voltages):
        cur_time = self._start_time + self._resolution * time_step
        if self._bufs is None:
            self._bufs = [CircularBufferHelper(self._window_size) for _ in range(len(self._node_names))]
            self._metric_2_violation_counts = [0] * len(self._node_names)
            self._metric_5_min_violations = [None] * len(self._node_names)
            self._metric_5_max_violations = [None] * len(self._node_names)

        count_outside_range_a = 0
        any_outside_range_b = False
        any_moving_avg_violates_range_a = False
        # The voltages passed include all nodes. self._node_indices has the ones
        # being tracked here.
        for i, node_index in enumerate(self._node_indices):
            voltage = voltages[node_index]
            buf = self._bufs[i]
            buf.append(voltage.value)
            if not any_moving_avg_violates_range_a and self._is_outside_range_a(buf.average()):
                any_moving_avg_violates_range_a = True

            if self._is_outside_range_a(voltage.value):
                count_outside_range_a += 1
                self._metric_2_violation_counts[i] += 1
            if self._is_outside_range_b(voltage.value):
                any_outside_range_b = True
            if self._metric_5_min_violations[i] is None:
                self._metric_5_min_violations[i] = voltage.value
                self._metric_5_max_violations[i] = voltage.value
            elif voltage.value < self._metric_5_min_violations[i]:
                self._metric_5_min_violations[i] = voltage.value
            elif voltage.value > self._metric_5_max_violations[i]:
                self._metric_5_max_violations[i] = voltage.value

        if count_outside_range_a > 0:
            if not any_outside_range_b:
                self._metric_1_time_steps.append(cur_time)

            percent_violations = count_outside_range_a / len(self._node_names) * 100
            self._metric_4_violations.append((cur_time, percent_violations))

        if any_moving_avg_violates_range_a:
            self._metric_3_time_steps.append(cur_time)

        if any_outside_range_b:
            self._num_metric_6_time_points_outside_range_b += 1

    def _is_outside_range_a(self, value):
        return value < self._range_a_limits.min or value > self._range_a_limits.max

    def _is_outside_range_b(self, value):
        return value < self._range_b_limits.min or value > self._range_b_limits.max

    def increment_steps(self):
        self._num_time_points += 1

    def set_node_info(self, node_names, node_indices):
        self._node_names = node_names
        self._node_indices = node_indices


class NodeVoltageMetrics:
    """Stores node voltage metrics in memory.

    The metrics are defined in this paper:
    https://www.sciencedirect.com/science/article/pii/S0306261920311351

    """

    FILENAME = "voltage_metrics.json"

    def __init__(self, prop, start_time, resolution, window_size, store_per_element_data):
        self._start_time = start_time
        self._resolution = resolution
        self._window_size = window_size
        self._num_time_points = 0
        self._metrics = {
            "primary": NodeVoltageMetricsByType(prop, start_time, resolution, window_size),
            "secondary": NodeVoltageMetricsByType(prop, start_time, resolution, window_size),
        }
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
        if not self._metrics["primary"].has_data():
            logger.error("Cannot generate report with no data")
            return

        metrics = VoltageMetricsByBusTypeModel(
            primaries=self._metrics["primary"].generate(self._store_per_element_data),
            secondaries=self._metrics["secondary"].generate(self._store_per_element_data),
        )

        filename = Path(path) / self.FILENAME
        with open(filename, "w") as f_out:
            f_out.write(metrics.model_dump_json())
            f_out.write("\n")

    def increment_steps(self):
        """Increment the time step counter."""
        for metric in self._metrics.values():
            metric.increment_steps()

    def set_node_info(self, primary_names, primary_indices, secondary_names, secondary_indices):
        self._metrics["primary"].set_node_info(primary_names, primary_indices)
        self._metrics["secondary"].set_node_info(secondary_names, secondary_indices)

    def update(self, time_step, voltages):
        """Update the metrics for the time step.

        Parameters
        ----------
        time_step : int
        voltages : list
            list of ValueStorageBase

        """
        for metric in self._metrics.values():
            metric.update(time_step, voltages)
