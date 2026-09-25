"""Shared declarations for migrated controller components."""

from collections.abc import Mapping
from typing import Any

import numpy as np

from pydss.openmdao_components import ControllerExplicitComponent, VariableSpec

MEASUREMENTS = (
    VariableSpec("measurement_voltage_pu"),
    VariableSpec("measurement_active_power"),
    VariableSpec("measurement_reactive_power"),
    VariableSpec("time_seconds"),
)
COMMANDS = (
    VariableSpec("command_active_power"),
    VariableSpec("command_reactive_power"),
    VariableSpec("command_enabled", val=1.0),
    VariableSpec("diagnostic_residual"),
)


class MigratedController(ControllerExplicitComponent):
    """Pure controller shell with an explicit state commit boundary."""

    def setup(self) -> None:
        self._step_count = 0
        self.options["input_specs"] = self.input_specs()
        self.options["output_specs"] = self.output_specs()
        super().setup()

    def input_specs(self) -> tuple[VariableSpec, ...]:
        return MEASUREMENTS

    def output_specs(self) -> tuple[VariableSpec, ...]:
        return COMMANDS

    def compute_commands(self, inputs) -> Mapping[str, Any]:
        settings = self.options["settings"] or {}
        active_power = float(np.asarray(inputs["measurement_active_power"]))
        reactive_power = float(np.asarray(inputs["measurement_reactive_power"]))
        return {
            "command_active_power": settings.get("active_power", active_power),
            "command_reactive_power": settings.get("reactive_power", reactive_power),
            "command_enabled": float(settings.get("enabled", 1.0)),
            "diagnostic_residual": 0.0,
        }

    def commit_step(self) -> None:
        self._step_count += 1

    @property
    def step_count(self) -> int:
        return self._step_count
