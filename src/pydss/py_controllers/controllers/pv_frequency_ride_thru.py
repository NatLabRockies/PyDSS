from collections.abc import Mapping
from typing import Any
from pydss.openmdao_components import ControllerExplicitComponent, VariableSpec


class PvFrequencyRideThru(ControllerExplicitComponent):
    """OpenMDAO PV frequency ride-through component."""

    def setup(self) -> None:
        self._connected = True
        self._violation_start = None
        self._pending_state = None
        self._step_count = 0
        super().setup()

    def input_specs(self) -> tuple[VariableSpec, ...]:
        return (
            VariableSpec("measurement_frequency_hz"),
            VariableSpec("measurement_active_power"),
            VariableSpec("measurement_reactive_power"),
            VariableSpec("time_seconds"),
        )

    def output_specs(self) -> tuple[VariableSpec, ...]:
        return (
            VariableSpec("command_active_power"),
            VariableSpec("command_reactive_power"),
            VariableSpec("command_enabled", val=1.0),
            VariableSpec("diagnostic_residual"),
        )

    def compute_commands(self, inputs) -> Mapping[str, Any]:
        if not hasattr(self, "_violation_start"):
            self._connected = True
            self._violation_start = None
            self._pending_state = None
            self._step_count = 0
        settings = self.options["settings"] or {}
        frequency = self.input_value(inputs, "measurement_frequency_hz")
        time = self.input_value(inputs, "time_seconds")
        lower = float(settings.get("continuous_f_lower_hz", settings.get("f_lower", 59.3)))
        upper = float(settings.get("continuous_f_upper_hz", settings.get("f_upper", 60.5)))
        delay = float(settings.get("trip_delay_sec", settings.get("trip_deadtime_sec", 0.0)))
        violation_start = self._violation_start
        if lower <= frequency <= upper:
            violation_start = None
        elif violation_start is None:
            violation_start = time
        connected = self._connected and not (
            violation_start is not None and time - violation_start >= delay
        )
        self._pending_state = (connected, violation_start)
        return {
            "command_active_power": self.input_value(inputs, "measurement_active_power")
            if connected
            else 0.0,
            "command_reactive_power": self.input_value(inputs, "measurement_reactive_power")
            if connected
            else 0.0,
            "command_enabled": float(connected),
            "diagnostic_residual": float(connected != self._connected),
        }

    def commit_step(self) -> None:
        if self._pending_state is not None:
            self._connected, self._violation_start = self._pending_state
            self._pending_state = None
        self._step_count += 1

    @property
    def step_count(self) -> int:
        return self._step_count
