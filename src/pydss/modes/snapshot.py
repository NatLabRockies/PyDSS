from pydss.modes.solver_base import SolverBase
from pydss.simulation_input_models import ProjectModel


class Snapshot(SolverBase):
    def __init__(self, dss_instance, settings: ProjectModel):
        super().__init__(dss_instance, settings)
        self._dss_solution.Mode(0)
        self._dss_instance.utils.run_command(
            "Set ControlMode={}".format(settings.control_mode.value)
        )
        self._dss_solution.MaxControlIterations(settings.max_control_iterations)
        return

    def re_solve(self):
        self._dss_solution.SolveNoControl()
        return self._dss_solution.Converged()

    def simulation_steps(self):
        return 1, self._start_time, self._end_time

    def solve(self):
        self._dss_solution.Solve()
        return self._dss_solution.Converged()

    def inc_step(self):
        return self._dss_solution.Solve()

    def solve_for(self):
        pass

    def reset(self):
        pass


Snapshot.SimulationSteps = Snapshot.simulation_steps
Snapshot.Solve = Snapshot.solve
Snapshot.IncStep = Snapshot.inc_step
Snapshot.SolveFor = Snapshot.solve_for
Snapshot.reSolve = Snapshot.re_solve
