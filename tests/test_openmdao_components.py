import numpy as np
import openmdao.api as om
import pytest

from pydss.openmdao_components import (
    CircuitAdapter,
    CircuitExplicitComponent,
    ControllerExplicitComponent,
    OpenDSSCircuitAdapter,
    VariableSpec,
)
from pydss.openmdao_model import build_openmdao_problem


class FakeCircuit(CircuitAdapter):
    def __init__(self):
        self.command = 0.0
        self.apply_count = 0
        self.solve_count = 0
        self.commit_count = 0

    def apply_commands(self, commands):
        self.apply_count += 1
        self.command = float(commands["command"])

    def solve(self):
        self.solve_count += 1
        return True

    def read_measurements(self, names):
        assert names == ("voltage",)
        return {"voltage": 1.0 + self.command}

    def commit_step(self):
        self.commit_count += 1


class VoltageController(ControllerExplicitComponent):
    def setup(self):
        super().setup()
        self.add_input("target", val=1.0)

    def compute_commands(self, inputs):
        return {"command": inputs["target"] - inputs["voltage"]}


def test_openmdao_requires_positive_iteration_limit():
    circuit = CircuitExplicitComponent(
        adapter=FakeCircuit(),
        measurement_specs=(VariableSpec("voltage"),),
    )

    with pytest.raises(ValueError, match="at least 1"):
        build_openmdao_problem(circuit, max_iterations=0)


def test_openmdao_controller_circuit_cycle_and_commit():
    adapter = FakeCircuit()
    circuit = CircuitExplicitComponent(
        adapter=adapter,
        command_specs=(VariableSpec("command"),),
        measurement_specs=(VariableSpec("voltage"),),
    )
    controller = VoltageController(
        input_specs=(VariableSpec("voltage"),),
        output_specs=(VariableSpec("command"),),
    )
    problem = build_openmdao_problem(
        circuit,
        [("controller", controller)],
        [("circuit.voltage", "controller.voltage"), ("controller.command", "circuit.command")],
        max_iterations=20,
        tolerance=1e-10,
    )

    problem.run_model()

    np.testing.assert_allclose(problem.get_val("circuit.voltage"), 1.0, atol=1e-7)
    assert adapter.apply_count == adapter.solve_count
    assert adapter.commit_count == 0

    problem.model.commit_step()

    assert adapter.commit_count == 1


def test_openmdao_controller_cycle_reports_nonconvergence():
    circuit = CircuitExplicitComponent(
        adapter=FakeCircuit(),
        command_specs=(VariableSpec("command"),),
        measurement_specs=(VariableSpec("voltage"),),
    )
    controller = VoltageController(
        input_specs=(VariableSpec("voltage"),),
        output_specs=(VariableSpec("command"),),
    )
    problem = build_openmdao_problem(
        circuit,
        [("controller", controller)],
        [("circuit.voltage", "controller.voltage"), ("controller.command", "circuit.command")],
        max_iterations=1,
        tolerance=1e-10,
    )

    with pytest.raises(om.AnalysisError, match="failed to converge"):
        problem.run_model()


class FakeDssElement:
    Bus = ("source",)

    def __init__(self):
        self.parameters = {}

    def SetParameter(self, name, value):
        self.parameters[name] = value

    def GetValue(self, name):
        assert name == "Powers"
        return [2.0, 3.0]


class FakeDss:
    class Circuit:
        active_bus = None

        @classmethod
        def SetActiveBus(cls, name):
            cls.active_bus = name

    class Bus:
        @staticmethod
        def puVmagAngle():
            return [1.02, 0.0]

    class Solution:
        @staticmethod
        def Converged():
            return True


class FakeSolver:
    def __init__(self):
        self.solve_count = 0
        self.time_index = 0

    def reSolve(self):
        self.solve_count += 1

    def IncStep(self):
        self.time_index += 1


def test_opendss_circuit_adapter_maps_generic_io():
    element = FakeDssElement()
    adapter = OpenDSSCircuitAdapter(
        FakeDss(),
        FakeSolver(),
        {"PVSystem.pv1": element},
        {
            "command_active_power": ("PVSystem.pv1", "kW"),
            "command_reactive_power": ("PVSystem.pv1", "kvar"),
            "command_enabled": ("PVSystem.pv1", "enabled"),
        },
        {
            "measurement_voltage_pu": ("PVSystem.pv1", "measurement_voltage_pu"),
            "measurement_active_power": ("PVSystem.pv1", "measurement_active_power"),
            "measurement_reactive_power": ("PVSystem.pv1", "measurement_reactive_power"),
            "time_seconds": ("PVSystem.pv1", "time_seconds"),
        },
    )

    adapter.set_time(60.0)
    adapter.apply_commands({
        "command_active_power": np.asarray(4.0),
        "command_reactive_power": np.asarray(-1.0),
        "command_enabled": np.asarray(1.0),
    })

    assert element.parameters == {"kW": 4.0, "kvar": -1.0, "enabled": "Yes"}
    assert adapter.solve()
    assert adapter.read_measurements(tuple(adapter._measurement_map)) == {
        "measurement_voltage_pu": 1.02,
        "measurement_active_power": -2.0,
        "measurement_reactive_power": -3.0,
        "time_seconds": 60.0,
    }


def test_open_dss_resolve_does_not_advance_time_index():
    solver = FakeSolver()
    element = FakeDssElement()
    adapter = OpenDSSCircuitAdapter(
        FakeDss(), solver, {"PVSystem.pv1": element}, {}, {}
    )

    adapter.solve()
    adapter.solve()

    assert solver.solve_count == 2
    assert solver.time_index == 0

    solver.IncStep()

    assert solver.time_index == 1