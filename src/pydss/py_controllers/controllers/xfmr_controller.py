from collections.abc import Mapping
from typing import Any

from pydss.openmdao_components import ControllerExplicitComponent, VariableSpec


class XfmrController(ControllerExplicitComponent):
    """OpenMDAO transformer regulator command component."""

    def setup(self) -> None:
        self._locked = False
        self._pending_locked = None
        self._step_count = 0
        super().setup()

    def input_specs(self) -> tuple[VariableSpec, ...]:
        return (VariableSpec("measurement_active_power"), VariableSpec("time_seconds"))

    def output_specs(self) -> tuple[VariableSpec, ...]:
        return (VariableSpec("command_enabled", val=1.0), VariableSpec("diagnostic_residual"))

    def compute_commands(self, inputs) -> Mapping[str, Any]:
        settings = self.options["settings"] or {}
        reverse_power_locking = bool(
            settings.get("rpf_locking", settings.get("RPF locking", False))
        )
        power = self.input_value(inputs, "measurement_active_power")
        locked = reverse_power_locking and power < 0.0
        self._pending_locked = locked
        return {
            "command_enabled": float(not locked),
            "diagnostic_residual": float(locked != self._locked),
        }

    def commit_step(self) -> None:
        if self._pending_locked is not None:
            self._locked = self._pending_locked
            self._pending_locked = None
        self._step_count += 1

    @property
    def step_count(self) -> int:
        return self._step_count


def __getattr__(name: str):
    if name == "xfmrController":
        return XfmrController
    raise AttributeError(name)
