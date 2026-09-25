from collections.abc import Mapping
from typing import Any
import math

from pydss.openmdao_components import ControllerExplicitComponent, VariableSpec


class PvController(ControllerExplicitComponent):
    """OpenMDAO PV controller for declared voltage and power measurements."""

    def setup(self) -> None:
        self._pending_reactive = None
        self._committed_reactive = 0.0
        self._iteration_reactive = 0.0
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
        return (VariableSpec("command_reactive_power"), VariableSpec("diagnostic_residual"))

    def compute_commands(self, inputs) -> Mapping[str, Any]:
        settings = self.options["settings"] or {}
        voltage = self.input_value(inputs, "measurement_voltage_pu")
        active = self.input_value(inputs, "measurement_active_power")
        reactive = self.input_value(inputs, "measurement_reactive_power")
        rated_kva = float(self.options["rated_kva"])
        reactive_pu = reactive / rated_kva if rated_kva else 0.0
        u_min = float(settings.get("u_min", settings.get("uMin", 0.94)))
        u_db_min = float(settings.get("u_db_min", settings.get("uDbMin", 0.97)))
        u_db_max = float(settings.get("u_db_max", settings.get("uDbMax", 1.03)))
        u_max = float(settings.get("u_max", settings.get("uMax", 1.06)))
        q_limit = abs(float(settings.get("q_lim_pu", settings.get("QlimPU", 0.44))))
        if voltage <= u_min:
            target = q_limit
        elif voltage < u_db_min:
            target = q_limit * (u_db_min - voltage) / (u_db_min - u_min)
        elif voltage <= u_db_max:
            target = 0.0
        elif voltage < u_max:
            target = -q_limit * (voltage - u_db_max) / (u_max - u_db_max)
        else:
            target = -q_limit
        damping = float(settings.get("damp_coef", settings.get("DampCoef", 0.8)))
        target = reactive_pu + (target - reactive_pu) * 0.5 / damping
        target += (reactive_pu - self._iteration_reactive) * 0.1 / damping
        self._iteration_reactive = reactive_pu
        if bool(settings.get("enable_pf_limit", settings.get("Enable PF limit", False))):
            pf_limit = float(settings.get("pf_lim", settings.get("PFlim", 0.9)))
            target = max(
                -abs(active * math.tan(math.acos(pf_limit))),
                min(abs(active * math.tan(math.acos(pf_limit))), target),
            )
        command_reactive = target * rated_kva
        self._pending_reactive = command_reactive
        return {
            "command_reactive_power": command_reactive,
            "diagnostic_residual": command_reactive - reactive,
        }

    def commit_step(self) -> None:
        self._committed_reactive = self._iteration_reactive
        self._pending_reactive = None
        self._step_count += 1

    def reset_step(self) -> None:
        self._iteration_reactive = self._committed_reactive

    @property
    def step_count(self) -> int:
        return self._step_count
