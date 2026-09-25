from datetime import timedelta

from pydss.modes.solver_base import SolverBase
from pydss.simulation_input_models import ProjectModel
from pydss.utils.dss_utils import get_load_shape_resolution_secs


class QSTS(SolverBase):
    def __init__(self, dss_instance, settings: ProjectModel):
        super().__init__(dss_instance, settings)
        self._dss_solution.Mode(2)
        self._dss_instance.utils.run_command(
            "Set ControlMode={}".format(settings.control_mode.value)
        )
        self._dss_solution.Number(1)
        self._dss_solution.StepSize(self._step_resolution)
        self._dss_solution.MaxControlIterations(settings.max_control_iterations)

        start_time_hours = self._hour + self._second / 3600.0
        load_shape_resolution_seconds = get_load_shape_resolution_secs()
        if load_shape_resolution_seconds == self._step_resolution:
            # I don't know why this is needed in this case.
            # The first data point gets skipped without it.
            # FIXME
            start_time_hours += self._step_resolution / 3600.0
        self._dss_solution.DblHour(start_time_hours)
        return

    def solve_for(self, start_time, time_step):
        hour = int(start_time / 60)
        minute = start_time % 60
        self._dss_solution.DblHour(hour + minute / 60.0)
        self._dss_solution.Number(time_step)
        self._dss_solution.Solve()
        return self._dss_solution.Converged()

    def inc_step(self):
        self._dss_solution.StepSize(self._step_resolution)
        self._dss_solution.Solve()
        self._time = self._time + timedelta(seconds=self._step_resolution)
        self._hour = int(self._dss_solution.DblHour() // 1)
        self._second = (self._dss_solution.DblHour() % 1) * 60 * 60
        return self._dss_solution.Converged()

    def re_solve(self):
        self._dss_solution.StepSize(0)
        self._dss_solution.SolveNoControl()
        return self._dss_solution.Converged()

    def solve(self):
        self._dss_solution.StepSize(0)
        self._dss_solution.Solve()
        return self._dss_solution.Converged()

    def set_mode(self, mode):
        self._dss_instance.utils.run_command("Set Mode={}".format(mode))
        if mode.lower() == "yearly":
            self._dss_solution.Mode(2)
            self._dss_solution.DblHour(self._hour + self._second / 3600.0)
            self._dss_solution.Number(1)
            self._dss_solution.StepSize(self._step_resolution)
            self._dss_solution.MaxControlIterations(self._settings.project.max_control_iterations)

    def reset(self):
        pass


QSTS.SolveFor = QSTS.solve_for
QSTS.IncStep = QSTS.inc_step
QSTS.reSolve = QSTS.re_solve
QSTS.Solve = QSTS.solve
QSTS.setMode = QSTS.set_mode
