"""OpenMDAO problem construction and accepted-time-step lifecycle."""

from __future__ import annotations

from collections.abc import Iterable
from os import PathLike
from pathlib import Path

import openmdao.api as om

from pydss.openmdao_components import CircuitExplicitComponent, ControllerExplicitComponent


class PyDSSOpenMDAOGroup(om.Group):
    """Circuit/controller group with OpenMDAO-owned nonlinear convergence."""

    def initialize(self) -> None:
        self.options.declare("circuit", recordable=False)
        self.options.declare("controllers", types=(tuple, list), default=(), recordable=False)
        self.options.declare("connections", types=(tuple, list), default=(), recordable=False)

    def setup(self) -> None:
        circuit: CircuitExplicitComponent = self.options["circuit"]
        for name, controller in self.options["controllers"]:
            self.add_subsystem(name, controller)
        # Controllers consume the previous OpenDSS measurements first. The
        # circuit is last so one solve sees the complete command batch.
        self.add_subsystem("circuit", circuit)
        for source, target in self.options["connections"]:
            self.connect(source, target)

    def commit_step(self) -> None:
        self.circuit.commit_step()
        for name, _ in self.options["controllers"]:
            subsystem = self._get_subsystem(name)
            subsystem.commit_step()

    def reset_step(self) -> None:
        self.circuit.reset_step()
        for name, _ in self.options["controllers"]:
            subsystem = self._get_subsystem(name)
            subsystem.reset_step()


def controller_circuit_variable(index: int, spec_name: str) -> str:
    """Return the deterministic circuit-side name for one controller variable."""
    return f"controller_{index}__{spec_name}"


def build_openmdao_problem(
    circuit: CircuitExplicitComponent,
    controllers: Iterable[tuple[str, ControllerExplicitComponent]] = (),
    connections: Iterable[tuple[str, str]] = (),
    *,
    max_iterations: int = 50,
    tolerance: float = 1e-6,
    reports: bool = False,
    work_dir: str | PathLike[str] | None = None,
    name: str | None = None,
) -> om.Problem:
    """Build and configure a PyDSS OpenMDAO problem."""

    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")

    model = PyDSSOpenMDAOGroup(
        circuit=circuit,
        controllers=tuple(controllers),
        connections=tuple(connections),
    )
    model.nonlinear_solver = om.NonlinearBlockGS(
        maxiter=max_iterations,
        atol=tolerance,
        rtol=tolerance,
        use_aitken=True,
        err_on_non_converge=True,
    )
    problem_options = {"reports": reports}
    if name is not None:
        problem_options["name"] = name
    if work_dir is not None:
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        problem_options["work_dir"] = work_dir
    problem = om.Problem(model=model, **problem_options)
    if reports:
        recorder_path = Path(work_dir or ".") / "openmdao_convergence.sql"
        if recorder_path.exists():
            recorder_path.unlink()
        recorder = om.SqliteRecorder(str(recorder_path))
        model.nonlinear_solver.add_recorder(recorder)
        model.nonlinear_solver.recording_options["record_abs_error"] = True
        model.nonlinear_solver.recording_options["record_rel_error"] = True
    problem.setup()
    return problem
