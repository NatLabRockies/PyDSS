from collections.abc import Mapping
from typing import Any
from pydss.openmdao_components import ControllerExplicitComponent, VariableSpec


class PvDynamic(ControllerExplicitComponent):
    """OpenMDAO boundary for an external dynamic PV model."""

    def setup(self) -> None:
        self._state = {"active": None, "reactive": None}
        self._pending_state = None
        self._step_count = 0
        super().setup()

    def input_specs(self) -> tuple[VariableSpec, ...]:
        return (VariableSpec("measurement_voltage_pu"), VariableSpec("measurement_active_power"),
                VariableSpec("measurement_reactive_power"), VariableSpec("time_seconds"))

    def output_specs(self) -> tuple[VariableSpec, ...]:
        return (VariableSpec("command_active_power"), VariableSpec("command_reactive_power"),
                VariableSpec("diagnostic_residual"))

    def compute_commands(self, inputs) -> Mapping[str, Any]:
        if not hasattr(self, "_state"):
            self._state = {"active": None, "reactive": None}
            self._pending_state = None
            self._step_count = 0
        settings = self.options["settings"] or {}
        active = float(inputs["measurement_active_power"])
        reactive = float(inputs["measurement_reactive_power"])
        response = max(0.0, min(1.0, float(settings.get("response_fraction", 1.0))))
        previous_active = active if self._state["active"] is None else self._state["active"]
        previous_reactive = reactive if self._state["reactive"] is None else self._state["reactive"]
        command_active = previous_active + response * (active - previous_active)
        command_reactive = previous_reactive + response * (reactive - previous_reactive)
        self._pending_state = {"active": command_active, "reactive": command_reactive}
        return {"command_active_power": command_active, "command_reactive_power": command_reactive,
                "diagnostic_residual": command_active - active}

    def commit_step(self) -> None:
        if self._pending_state is not None:
            self._state = self._pending_state
            self._pending_state = None
        self._step_count += 1

    @property
    def step_count(self) -> int:
        return self._step_count
