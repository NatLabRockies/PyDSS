from collections.abc import Mapping
from typing import Any
import math

from pydss.openmdao_components import ControllerExplicitComponent, VariableSpec


class DynamicVoltageSupport(ControllerExplicitComponent):
    """OpenMDAO component for dynamic voltage support command calculation."""

    def setup(self) -> None:
        self._state = {
            "voltage": 1.0,
            "active": None,
            "reactive": None,
            "initial_reactive": None,
            "fault_present": False,
        }
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
        voltage = self.input_value(inputs, "measurement_voltage_pu")
        active = self.input_value(inputs, "measurement_active_power")
        reactive = self.input_value(inputs, "measurement_reactive_power")
        initial_reactive = self._state["initial_reactive"]
        if initial_reactive is None:
            initial_reactive = reactive
        trv = max(float(settings.get("Trv", 0.001)), 1e-9)
        tinv = max(float(settings.get("Tinv", 0.001)), 1e-9)
        dt = float(settings.get("step_resolution_sec", 1.0))
        alpha_v = dt / (trv + dt)
        alpha_i = dt / (tinv + dt)
        filtered_voltage = self._state["voltage"] + alpha_v * (voltage - self._state["voltage"])
        error = filtered_voltage - 1.0
        lower_deadband = float(settings.get("dbd1", -0.1))
        upper_deadband = float(settings.get("dbd2", 0.1))
        in_deadband = lower_deadband < error < upper_deadband
        fault_present = self._state["fault_present"] or not in_deadband
        kvar = initial_reactive if in_deadband else reactive
        if not in_deadband and bool(settings.get("capacitive_support", True)):
            kvar += -error * float(settings.get("Kqv", 100.0))
        kva_rated = float(settings.get("kva", max(math.hypot(active, reactive), 1.0)))
        kvar = min(float(settings.get("kvar_max", 0.44)) * kva_rated, kvar)
        kvar = max(float(settings.get("kvar_min", -0.44)) * kva_rated, kvar)
        previous_active = active if self._state["active"] is None else self._state["active"]
        previous_reactive = reactive if self._state["reactive"] is None else self._state["reactive"]
        active_command = previous_active + alpha_i * (active - previous_active)
        reactive_command = previous_reactive + alpha_i * (kvar - previous_reactive)
        kva_limit = kva_rated
        if math.hypot(active_command, reactive_command) > kva_limit:
            active_command = math.copysign(
                math.sqrt(max(kva_limit**2 - reactive_command**2, 0.0)), active_command
            )
        if in_deadband and fault_present and abs(reactive_command - initial_reactive) < 1e-6:
            reactive_command = initial_reactive
            fault_present = False
        self._pending_state = {
            "voltage": filtered_voltage,
            "active": active_command,
            "reactive": reactive_command,
            "initial_reactive": initial_reactive,
            "fault_present": fault_present,
        }
        return {
            "command_active_power": active_command,
            "command_reactive_power": reactive_command,
            "command_enabled": 1.0,
            "diagnostic_residual": error,
        }

    def commit_step(self) -> None:
        if self._pending_state is not None:
            self._state = self._pending_state
            self._pending_state = None
        self._step_count += 1

    @property
    def step_count(self) -> int:
        return self._step_count
