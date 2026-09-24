from collections.abc import Mapping
from typing import Any

from pydss.openmdao_components import ControllerExplicitComponent, VariableSpec


class MotorStallSimple(ControllerExplicitComponent):
    """OpenMDAO simplified motor-stall command component."""

    def setup(self) -> None:
        self._state = {"stalled": False, "disconnected": False, "stall_start": None,
                       "disconnect_start": None, "base_active": None, "base_reactive": None}
        self._pending_state = None
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
            VariableSpec("command_enabled", val=1.0),
            VariableSpec("diagnostic_residual"),
        )

    def compute_commands(self, inputs) -> Mapping[str, Any]:
        settings = self.options["settings"] or {}
        voltage = float(inputs["measurement_voltage_pu"])
        active = float(inputs["measurement_active_power"])
        reactive = float(inputs["measurement_reactive_power"])
        time = float(inputs["time_seconds"])
        state = self._state
        base_active = active if state["base_active"] is None else state["base_active"]
        base_reactive = reactive if state["base_reactive"] is None else state["base_reactive"]
        stall_voltage = float(settings.get("v_stall", 0.55))
        protection_time = float(settings.get("t_protection", 0.95))
        reconnect_time = float(settings.get("t_reconnect", 6.0))
        p_fault = float(settings.get("p_fault", 3.5))
        q_fault = float(settings.get("q_fault", 5.0))

        stalled = bool(state["stalled"])
        disconnected = bool(state["disconnected"])
        stall_start = state["stall_start"]
        disconnect_start = state["disconnect_start"]
        if not stalled and not disconnected and voltage < stall_voltage:
            stalled, stall_start = True, time
        if stalled and stall_start is not None and time - stall_start > protection_time:
            stalled, disconnected, disconnect_start = False, True, time
        if disconnected and disconnect_start is not None:
            if time - disconnect_start > reconnect_time and voltage >= stall_voltage:
                disconnected, disconnect_start = False, None

        if disconnected:
            active_command = reactive_command = 0.0
        elif stalled:
            active_command = base_active * p_fault
            reactive_command = base_reactive * q_fault
        else:
            active_command, reactive_command = base_active, base_reactive

        self._pending_state = {
            "stalled": stalled,
            "disconnected": disconnected,
            "stall_start": stall_start,
            "disconnect_start": disconnect_start,
            "base_active": base_active,
            "base_reactive": base_reactive,
        }
        return {
            "command_active_power": active_command,
            "command_reactive_power": reactive_command,
            "command_enabled": float(not disconnected),
            "diagnostic_residual": 0.0,
        }

    def commit_step(self) -> None:
        if self._pending_state is not None:
            self._state = self._pending_state
            self._pending_state = None
        self._step_count += 1

    @property
    def step_count(self) -> int:
        return self._step_count
