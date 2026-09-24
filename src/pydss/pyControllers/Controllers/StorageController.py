from collections.abc import Mapping
from typing import Any

from pydss.openmdao_components import ControllerExplicitComponent, VariableSpec


class StorageController(ControllerExplicitComponent):
    """OpenMDAO storage dispatch component with committed step state."""

    def setup(self) -> None:
        self._previous_active = 0.0
        self._pending_active = None
        self._step_count = 0
        super().setup()

    def input_specs(self) -> tuple[VariableSpec, ...]:
        return (VariableSpec("measurement_active_power"), VariableSpec("measurement_reactive_power"),
                VariableSpec("time_seconds"))

    def output_specs(self) -> tuple[VariableSpec, ...]:
        return (VariableSpec("command_active_power"), VariableSpec("command_reactive_power"),
                VariableSpec("diagnostic_residual"))

    def compute_commands(self, inputs) -> Mapping[str, Any]:
        settings = self.options["settings"] or {}
        measured = float(inputs["measurement_active_power"])
        control = str(settings.get("control", settings.get("mode", "None"))).lower()
        if control in {"rt", "realtime", "real_time"}:
            target = float(settings.get("kw_out", settings.get("%kWOut", measured)))
        elif control in {"sh", "scheduled", "schedule"}:
            schedule = settings.get("schedule", settings.get("Schedule", ()))
            index = min(len(schedule) - 1, max(0, int(float(inputs["time_seconds"]) / max(float(settings.get("schedule_period_sec", 3600.0)), 1.0)))) if schedule else 0
            target = float(schedule[index]) if schedule else measured
        elif control in {"ps", "peak_shaving", "peakshaving"}:
            upper = float(settings.get("ps_ub", settings.get("PS_ub", measured)))
            target = measured - max(0.0, measured - upper) * float(settings.get("damp_coef", settings.get("DampCoef", 1.0)))
        else:
            target = float(settings.get("active_power", measured))
        self._pending_active = target
        return {"command_active_power": target, "command_reactive_power": float(inputs["measurement_reactive_power"]),
                "diagnostic_residual": target - self._previous_active}

    def commit_step(self) -> None:
        if self._pending_active is not None:
            self._previous_active = self._pending_active
            self._pending_active = None
        self._step_count += 1

    @property
    def step_count(self) -> int:
        return self._step_count
