from collections.abc import Mapping
from typing import Any

from pydss.openmdao_components import ControllerExplicitComponent, VariableSpec


class FaultController(ControllerExplicitComponent):
    """OpenMDAO component that emits a time-windowed fault command."""

    def setup(self) -> None:
        self._fault_enabled = False
        self._pending_fault_enabled = None
        self._step_count = 0
        super().setup()

    def input_specs(self) -> tuple[VariableSpec, ...]:
        return (VariableSpec("time_seconds"),)

    def output_specs(self) -> tuple[VariableSpec, ...]:
        return (VariableSpec("command_enabled", val=0.0), VariableSpec("diagnostic_residual"))

    def compute_commands(self, inputs) -> Mapping[str, Any]:
        settings = self.options["settings"] or {}
        time = float(inputs["time_seconds"])
        start = float(settings.get("start_time_seconds", settings.get("Fault start time (sec)", 0.0)))
        duration = float(settings.get("duration_seconds", settings.get("Fault duration (sec)", 0.0)))
        enabled = start <= time < start + duration
        self._pending_fault_enabled = enabled
        return {"command_enabled": float(enabled), "diagnostic_residual": float(enabled != self._fault_enabled)}

    def commit_step(self) -> None:
        if self._pending_fault_enabled is not None:
            self._fault_enabled = self._pending_fault_enabled
            self._pending_fault_enabled = None
        self._step_count += 1

    @property
    def step_count(self) -> int:
        return self._step_count
