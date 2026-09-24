from collections.abc import Mapping
from typing import Any
from pydss.openmdao_components import ControllerExplicitComponent, VariableSpec


class MotorStall(ControllerExplicitComponent):
    """OpenMDAO motor-stall command component."""

    def setup(self) -> None:
        self._state = "running"
        self._stall_start = None
        self._trip_time = None
        self._pending_state = None
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
        voltage = float(inputs["measurement_voltage_pu"])
        active = float(inputs["measurement_active_power"])
        reactive = float(inputs["measurement_reactive_power"])
        time = float(inputs["time_seconds"])
        stall_voltage = float(settings.get("v_stall", 0.55))
        protection = float(settings.get("t_protection", settings.get("t_stall", 0.95)))
        reconnect = float(settings.get("t_reconnect", settings.get("t_restart", 6.0)))
        state, stall_start, trip_time = self._state, self._stall_start, self._trip_time
        if state == "running" and voltage < stall_voltage:
            state, stall_start = "stalled", time
        if state == "stalled" and stall_start is not None and time - stall_start >= protection:
            state, trip_time = "tripped", time
        if state == "tripped" and voltage >= float(settings.get("v_rstrt", 0.95)) and trip_time is not None and time - trip_time >= reconnect:
            state, stall_start, trip_time = "running", None, None
        if state == "stalled":
            active *= float(settings.get("p_fault", 3.5))
            reactive *= float(settings.get("q_fault", 5.0))
        enabled = state != "tripped"
        self._pending_state = (state, stall_start, trip_time)
        return {"command_active_power": active if enabled else 0.0, "command_reactive_power": reactive if enabled else 0.0,
                "command_enabled": float(enabled), "diagnostic_residual": float(state != self._state)}

    def commit_step(self) -> None:
        if self._pending_state is not None:
            self._state, self._stall_start, self._trip_time = self._pending_state
            self._pending_state = None
        self._step_count += 1

    @property
    def step_count(self) -> int:
        return self._step_count
