"""OpenMDAO components used to couple PyDSS controllers and OpenDSS."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import openmdao.api as om


@dataclass(frozen=True)
class VariableSpec:
    """Description of one scalar or vector exchanged with an OpenMDAO component."""

    name: str
    shape: tuple[int, ...] = ()
    units: str | None = None
    val: Any = 0.0

    @property
    def size(self) -> int:
        return int(np.prod(self.shape)) if self.shape else 1


class CircuitAdapter(ABC):
    """Backend contract for a circuit component."""

    @abstractmethod
    def apply_commands(self, commands: Mapping[str, np.ndarray]) -> None:
        """Apply controller and exogenous commands to the circuit."""

    @abstractmethod
    def solve(self) -> bool:
        """Solve the circuit once and return backend convergence."""

    @abstractmethod
    def read_measurements(self, names: tuple[str, ...]) -> Mapping[str, Any]:
        """Read measurements after a successful circuit solve."""

    def commit_step(self) -> None:
        """Commit backend state after an accepted OpenMDAO time step."""

    def reset_step(self) -> None:
        """Discard transient state before a new OpenMDAO time step."""


class OpenDSSCircuitAdapter(CircuitAdapter):
    """Adapt the existing OpenDSS instance and element wrappers to OpenMDAO."""

    def __init__(self, dss_instance, solver, elements, command_map, measurement_map):
        self._dss_instance = dss_instance
        self._solver = solver
        self._elements = elements
        self._command_map = command_map
        self._measurement_map = measurement_map
        self._time_seconds = 0.0

    def set_time(self, time_seconds: float) -> None:
        self._time_seconds = float(time_seconds)

    def apply_commands(self, commands: Mapping[str, np.ndarray]) -> None:
        for name, value in commands.items():
            element_name, parameter = self._command_map[name]
            element = self._elements[element_name]
            scalar = float(np.asarray(value).reshape(-1)[0])
            if parameter == "enabled":
                scalar = "Yes" if scalar else "No"
            element.SetParameter(parameter, scalar)

    def solve(self) -> bool:
        self._solver.reSolve()
        return bool(self._dss_instance.Solution.Converged())

    def read_measurements(self, names: tuple[str, ...]) -> Mapping[str, Any]:
        values = {}
        for name in names:
            element_name, measurement = self._measurement_map[name]
            if measurement == "time_seconds":
                values[name] = self._time_seconds
                continue
            if measurement == "measurement_frequency_hz":
                values[name] = float(self._dss_instance.Solution.Frequency())
                continue

            element = self._elements[element_name]
            if measurement == "measurement_voltage_pu":
                self._dss_instance.Circuit.SetActiveBus(element.Bus[0])
                voltage_values = np.asarray(self._dss_instance.Bus.puVmagAngle()).reshape(-1)
                values[name] = float(np.max(voltage_values[::2]))
            elif measurement == "measurement_active_power":
                values[name] = self._element_power(element, 0)
            elif measurement == "measurement_reactive_power":
                values[name] = self._element_power(element, 1)
            else:
                raise KeyError(f"Unsupported OpenDSS measurement {measurement}")
        return values

    @staticmethod
    def _element_power(element, index: int) -> float:
        powers = element.GetValue("Powers")
        values = np.asarray(powers).reshape(-1)
        return float(-np.sum(values[index::2]))


class CircuitExplicitComponent(om.ExplicitComponent):
    """Explicit OpenMDAO representation of one OpenDSS circuit evaluation."""

    def initialize(self) -> None:
        self.options.declare("adapter", recordable=False)
        self.options.declare("command_specs", types=(tuple, list), default=())
        self.options.declare("measurement_specs", types=(tuple, list), default=())

    def setup(self) -> None:
        self._command_specs = tuple(self.options["command_specs"])
        self._measurement_specs = tuple(self.options["measurement_specs"])
        for spec in self._command_specs:
            self.add_input(spec.name, shape=spec.shape or None, units=spec.units, val=spec.val)
        for spec in self._measurement_specs:
            self.add_output(spec.name, shape=spec.shape or None, units=spec.units, val=spec.val)

    def compute(self, inputs, outputs) -> None:
        commands = {spec.name: np.asarray(inputs[spec.name]).copy() for spec in self._command_specs}
        adapter: CircuitAdapter = self.options["adapter"]
        try:
            adapter.apply_commands(commands)
            if not adapter.solve():
                raise om.AnalysisError("OpenDSS circuit solve did not converge")
            measurements = adapter.read_measurements(tuple(spec.name for spec in self._measurement_specs))
        except om.AnalysisError:
            raise
        except Exception as exc:
            raise om.AnalysisError(f"OpenDSS circuit evaluation failed: {exc}") from exc
        for spec in self._measurement_specs:
            if spec.name not in measurements:
                raise om.AnalysisError(f"Circuit adapter did not provide measurement {spec.name}")
            outputs[spec.name] = measurements[spec.name]

    def commit_step(self) -> None:
        self.options["adapter"].commit_step()

    def reset_step(self) -> None:
        self.options["adapter"].reset_step()


class ControllerExplicitComponent(om.ExplicitComponent, ABC):
    """Base class for controllers with OpenMDAO-owned inputs and outputs."""

    def initialize(self) -> None:
        self.options.declare("input_specs", types=(tuple, list), default=())
        self.options.declare("output_specs", types=(tuple, list), default=())
        self.options.declare("settings", default=None, recordable=False)
        self.options.declare("element_name", default="", types=str, recordable=False)
        self.options.declare("rated_kva", default=1.0, types=(int, float), recordable=False)

    def setup(self) -> None:
        self._input_specs = tuple(self.options["input_specs"]) or tuple(self.input_specs())
        self._output_specs = tuple(self.options["output_specs"]) or tuple(self.output_specs())
        for spec in self._input_specs:
            self.add_input(spec.name, shape=spec.shape or None, units=spec.units, val=spec.val)
        for spec in self._output_specs:
            self.add_output(spec.name, shape=spec.shape or None, units=spec.units, val=spec.val)

    def compute(self, inputs, outputs) -> None:
        values = self.compute_commands(inputs)
        for spec in self._output_specs:
            if spec.name not in values:
                raise om.AnalysisError(f"Controller did not provide command {spec.name}")
            outputs[spec.name] = values[spec.name]

    def input_specs(self) -> tuple[VariableSpec, ...]:
        """Return the measurements and exogenous values consumed by the controller."""
        return ()

    def output_specs(self) -> tuple[VariableSpec, ...]:
        """Return the circuit commands and diagnostics produced by the controller."""
        return (VariableSpec("command.active_power"), VariableSpec("command.reactive_power"),
                VariableSpec("diagnostic.residual"))

    def command_parameters(self, element_class: str) -> Mapping[str, str]:
        """Return OpenDSS parameter names for this component's command outputs."""
        parameters = {
            "command_active_power": "kW",
            "command_reactive_power": "kvar",
            "command_enabled": "enabled",
            "command_state": "State",
            "command_power_factor": "pf",
        }
        if element_class.lower() == "pvsystem":
            parameters["command_active_power"] = "Pmpp"
        return parameters

    @abstractmethod
    def compute_commands(self, inputs) -> Mapping[str, Any]:
        """Calculate controller commands without accessing OpenDSS or solving."""

    def commit_step(self) -> None:
        """Commit state after a successful nonlinear solve."""

    def reset_step(self) -> None:
        """Reset transient state before a new time step."""