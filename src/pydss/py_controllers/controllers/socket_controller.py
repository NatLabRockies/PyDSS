from collections.abc import Mapping
from typing import Any
from pydss.openmdao_components import ControllerExplicitComponent, VariableSpec


class SocketController(ControllerExplicitComponent):
    """Explicit socket command boundary; I/O belongs outside nonlinear trials."""

    def setup(self) -> None:
        self._pending = None
        self._step_count = 0
        super().setup()

    def input_specs(self) -> tuple[VariableSpec, ...]:
        return (
            VariableSpec("measurement_active_power"),
            VariableSpec("measurement_reactive_power"),
            VariableSpec("time_seconds"),
        )

    def output_specs(self) -> tuple[VariableSpec, ...]:
        return (
            VariableSpec("command_active_power"),
            VariableSpec("command_reactive_power"),
            VariableSpec("diagnostic_residual"),
        )

    def compute_commands(self, inputs) -> Mapping[str, Any]:
        settings = self.options["settings"] or {}
        active = float(
            settings.get("active_power", self.input_value(inputs, "measurement_active_power"))
        )
        reactive = float(
            settings.get("reactive_power", self.input_value(inputs, "measurement_reactive_power"))
        )
        self._pending = (active, reactive)
        return {
            "command_active_power": active,
            "command_reactive_power": reactive,
            "diagnostic_residual": 0.0,
        }

    def commit_step(self) -> None:
        self._pending = None
        self._step_count += 1

    @property
    def step_count(self) -> int:
        return self._step_count
