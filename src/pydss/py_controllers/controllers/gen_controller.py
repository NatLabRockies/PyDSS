from collections.abc import Mapping
from typing import Any

from pydss.openmdao_components import ControllerExplicitComponent, VariableSpec


class GenController(ControllerExplicitComponent):
    """OpenMDAO generator controller using declared circuit measurements."""

    def setup(self) -> None:
        self._pending_reactive = None
        self._step_count = 0
        super().setup()

    def input_specs(self) -> tuple[VariableSpec, ...]:
        return (
            VariableSpec("measurement_voltage_pu"),
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
        voltage = self.input_value(inputs, "measurement_voltage_pu")
        active = self.input_value(inputs, "measurement_active_power")
        reactive = self.input_value(inputs, "measurement_reactive_power")
        q_limit = abs(float(settings.get("q_limit", settings.get("QlimPU", 1.0))))
        low = float(settings.get("u_min", settings.get("uMin", 0.94)))
        high = float(settings.get("u_max", settings.get("uMax", 1.06)))
        db_low = float(settings.get("u_db_min", settings.get("uDbMin", 0.97)))
        db_high = float(settings.get("u_db_max", settings.get("uDbMax", 1.03)))
        if voltage <= low:
            target = q_limit
        elif voltage < db_low:
            target = q_limit * (db_low - voltage) / (db_low - low)
        elif voltage <= db_high:
            target = 0.0
        elif voltage < high:
            target = -q_limit * (voltage - db_high) / (high - db_high)
        else:
            target = -q_limit
        damping = max(
            0.0, min(1.0, float(settings.get("damp_coef", settings.get("DampCoef", 1.0))))
        )
        command_reactive = reactive + (target - reactive) * damping
        self._pending_reactive = command_reactive
        return {
            "command_active_power": active,
            "command_reactive_power": command_reactive,
            "diagnostic_residual": command_reactive - reactive,
        }

    def commit_step(self) -> None:
        self._pending_reactive = None
        self._step_count += 1

    @property
    def step_count(self) -> int:
        return self._step_count
