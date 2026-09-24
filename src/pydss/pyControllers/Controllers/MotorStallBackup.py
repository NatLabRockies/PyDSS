from collections.abc import Mapping
from typing import Any
from pydss.openmdao_components import ControllerExplicitComponent, VariableSpec


class MotorStallBackup(ControllerExplicitComponent):
    """OpenMDAO backup motor-stall command component."""

    def setup(self) -> None:
        self._pending = None
        self._state = "running"
        self._step_count = 0
        super().setup()

    def input_specs(self) -> tuple[VariableSpec, ...]:
        return (VariableSpec("measurement_voltage_pu"), VariableSpec("measurement_active_power"),
                VariableSpec("measurement_reactive_power"), VariableSpec("time_seconds"))

    def output_specs(self) -> tuple[VariableSpec, ...]:
        return (VariableSpec("command_active_power"), VariableSpec("command_reactive_power"),
                VariableSpec("command_enabled", val=1.0), VariableSpec("diagnostic_residual"))

    def compute_commands(self, inputs) -> Mapping[str, Any]:
        settings = self.options["settings"] or {}
        enabled = float(inputs["measurement_voltage_pu"]) >= float(settings.get("v_stall", 0.55))
        state = "running" if enabled else "backup"
        self._pending = state
        active = float(inputs["measurement_active_power"])
        reactive = float(inputs["measurement_reactive_power"])
        if not enabled:
            active *= float(settings.get("p_fault", 3.5))
            reactive *= float(settings.get("q_fault", 5.0))
        return {"command_active_power": active if enabled else 0.0, "command_reactive_power": reactive if enabled else 0.0,
                "command_enabled": float(enabled), "diagnostic_residual": float(state != self._state)}

    def commit_step(self) -> None:
        if self._pending is not None:
            self._state = self._pending
            self._pending = None
        self._step_count += 1

    @property
    def step_count(self) -> int:
        return self._step_count
