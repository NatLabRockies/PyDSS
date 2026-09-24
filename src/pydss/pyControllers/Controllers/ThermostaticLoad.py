from collections.abc import Mapping
from typing import Any
import math

from pydss.openmdao_components import ControllerExplicitComponent, VariableSpec


class ThermostaticLoad(ControllerExplicitComponent):
    """OpenMDAO thermostatic load command component."""

    def setup(self) -> None:
        settings = self.options["settings"] or {}
        self._temperature = float(settings.get("initial_temperature", (float(settings.get("Tmin", 18.0)) + float(settings.get("Tmax", 30.0))) / 2.0))
        self._on = bool(settings.get("initial_on", True))
        self._pending_state = None
        self._step_count = 0
        super().setup()

    def input_specs(self) -> tuple[VariableSpec, ...]:
        return (VariableSpec("time_seconds"), VariableSpec("measurement_active_power"),)

    def output_specs(self) -> tuple[VariableSpec, ...]:
        return (VariableSpec("command_active_power"), VariableSpec("diagnostic_residual"))

    def compute_commands(self, inputs) -> Mapping[str, Any]:
        settings = self.options["settings"] or {}
        t_min = float(settings.get("t_min", settings.get("Tmin", 18.0)))
        t_max = float(settings.get("t_max", settings.get("Tmax", 30.0)))
        resistance = max(float(settings.get("r", settings.get("R", 1.0))), 1e-9)
        capacitance = max(float(settings.get("c", settings.get("C", 1.0))), 1e-9)
        ambient = 30.0 + 10.0 * math.sin(float(inputs["time_seconds"]) * 2.0 * math.pi / 86400.0)
        rated = float(settings.get("kw", inputs["measurement_active_power"]))
        delta = -(self._temperature - ambient) / (resistance * capacitance)
        if self._on:
            delta -= float(settings.get("mu", 0.0)) * rated / capacitance
        temperature = self._temperature + delta
        on = self._on
        if temperature > t_max:
            on = True
        elif temperature < t_min:
            on = False
        self._pending_state = (temperature, on)
        return {"command_active_power": rated if on else 0.0, "diagnostic_residual": temperature - self._temperature}

    def commit_step(self) -> None:
        if self._pending_state is not None:
            self._temperature, self._on = self._pending_state
            self._pending_state = None
        self._step_count += 1

    @property
    def step_count(self) -> int:
        return self._step_count
