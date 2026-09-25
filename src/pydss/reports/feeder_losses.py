from typing import Annotated, Dict
from datetime import timedelta
import math
import os

from pydantic import BaseModel, Field
from pydantic import ConfigDict
from loguru import logger

from pydss.reports.reports import ReportBase


class FeederLossesMetricsModel(BaseModel):
    """Data model for metrics describing feeder losses"""

    model_config = ConfigDict(
        title="FeederLossesMetricsModel",
        str_strip_whitespace=True,
        validate_assignment=True,
        validate_default=True,
        extra="forbid",
        use_enum_values=False,
    )

    total_losses_kwh: Annotated[
        float,
        Field(
            None,
            title="total_losses_kwh",
            description="Total losses in the circuit",
        ),
    ]
    line_losses_kwh: Annotated[
        float,
        Field(
            None,
            title="line_losses_kwh",
            description="Total line losses",
        ),
    ]
    transformer_losses_kwh: Annotated[
        float,
        Field(
            None,
            title="transformer_losses_kwh",
            description="Total transformer losses",
        ),
    ]
    total_load_demand_kwh: Annotated[
        float,
        Field(
            None,
            title="total_load_demand_kwh",
            description="Total power output of loads",
        ),
    ]


class SimulationFeederLossesMetricsModel(BaseModel):
    scenarios: Dict[str, FeederLossesMetricsModel] = Field(
        title="scenarios",
        description="Feeder losses by pydss scenario name",
    )


def compare_feeder_losses(
    metrics1: SimulationFeederLossesMetricsModel,
    metrics2: SimulationFeederLossesMetricsModel,
    rel_tol=0.000001,
):
    """Compares the values of two instances of FeederLossesMetricsModel.

    Returns
    -------
    bool
        Return True if they match.

    """
    match = True
    for scenario in metrics1.scenarios:
        for field in FeederLossesMetricsModel.model_fields:
            val1 = getattr(metrics1.scenarios[scenario], field)
            val2 = getattr(metrics2.scenarios[scenario], field)
            if not math.isclose(val1, val2, rel_tol=rel_tol):
                logger.error("field=%s mismatch %s : %s", field, val1, val2)
                match = False

    return match


class FeederLossesReport(ReportBase):
    """Reports the feeder losses.

    The report generates a feeder_losses.json output file.

    """

    FILENAME = "feeder_losses.json"
    NAME = "Feeder Losses"
    DEFAULTS = {
        "store_all_time_points": False,
    }

    def generate(self, output_dir):
        resolution = self._get_simulation_resolution()
        to_kwh = resolution / timedelta(hours=1)
        assert len(self._results.scenarios) >= 1
        scenarios = {}
        for scenario in self._results.scenarios:
            inputs = FeederLossesReport.get_inputs_from_defaults(self._settings, self.NAME)
            if inputs["store_all_time_points"]:
                scenarios[scenario.name] = self._generate_from_all_time_points(scenario, to_kwh)
            else:
                scenarios[scenario.name] = self._generate_from_in_memory_metrics(scenario, to_kwh)

        model = SimulationFeederLossesMetricsModel(scenarios=scenarios)
        filename = os.path.join(output_dir, self.FILENAME)
        with open(filename, "w") as f_out:
            f_out.write(model.model_dump_json(indent=2))
            f_out.write("\n")
        logger.info("Generated %s", filename)
        return filename

    def _generate_from_in_memory_metrics(self, scenario, to_kwh):
        total_losses_dict = scenario.get_summed_element_total("Circuits", "LossesSum")
        total_losses = (
            abs(next(iter(total_losses_dict.values()))) / 1000
        )  # OpenDSS reports total losses in Watts
        line_losses_dict = scenario.get_summed_element_total("Circuits", "LineLossesSum")
        line_losses = abs(next(iter(line_losses_dict.values())))
        transformer_losses = total_losses - line_losses
        total_load_power_dict = scenario.get_summed_element_total("Loads", "PowersSum")
        total_load_power = 0
        for val in total_load_power_dict.values():
            total_load_power += val.real

        # TODO: total losses as a percentage of total load demand?
        return FeederLossesMetricsModel(
            total_losses_kwh=total_losses * to_kwh,
            line_losses_kwh=line_losses * to_kwh,
            transformer_losses_kwh=transformer_losses * to_kwh,
            total_load_demand_kwh=total_load_power * to_kwh,
        )

    def _generate_from_all_time_points(self, scenario, to_kwh):
        df_losses = scenario.get_full_dataframe("Circuits", "Losses")
        assert len(df_losses.columns) == 1

        df_line_losses = scenario.get_full_dataframe("Circuits", "LineLosses")
        assert len(df_line_losses.columns) == 1
        df_loads_powers = scenario.get_full_dataframe("Loads", "Powers")
        total_losses = abs(df_losses.sum().sum()) / 1000  # OpenDSS reports total losses in Watts
        line_losses = abs(df_line_losses.sum().sum())
        transformer_losses = total_losses - line_losses
        return FeederLossesMetricsModel(
            total_losses_kwh=total_losses * to_kwh,
            line_losses_kwh=line_losses * to_kwh,
            transformer_losses_kwh=transformer_losses * to_kwh,
            total_load_demand_kwh=df_loads_powers.sum().sum() * to_kwh,
        )

    @staticmethod
    def get_required_exports(simulation_config):
        inputs = FeederLossesReport.get_inputs_from_defaults(
            simulation_config, FeederLossesReport.NAME
        )
        if inputs["store_all_time_points"]:
            return {
                "Circuits": [
                    {
                        "property": "Losses",
                        "store_values_type": "all",
                    },
                    {
                        "property": "LineLosses",
                        "store_values_type": "all",
                    },
                ],
                "Loads": [
                    {
                        "property": "Powers",
                        "store_values_type": "all",
                        "data_conversion": "abs_sum",
                    },
                ],
            }

        return {
            "Circuits": [
                {
                    "property": "Losses",
                    "store_values_type": "sum",
                    "sum_elements": True,
                },
                {
                    "property": "LineLosses",
                    "store_values_type": "sum",
                    "sum_elements": True,
                },
            ],
            "Loads": [
                {
                    "property": "Powers",
                    "store_values_type": "sum",
                    "sum_elements": True,
                    "data_conversion": "abs_sum",
                },
            ],
        }

    @staticmethod
    def get_required_scenario_names():
        return set()
