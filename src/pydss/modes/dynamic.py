from datetime import timedelta
import math

from loguru import logger

from pydss.modes.solver_base import SolverBase
from pydss.simulation_input_models import ProjectModel


class Dynamic(SolverBase):
    def __init__(self, dss_instance, settings: ProjectModel):
        super().__init__(dss_instance, settings)
        self.set_mode("Dynamic")
        self._dss_instance.utils.run_command(
            "Set ControlMode={}".format(settings.control_mode.value)
        )
        self._dss_solution.Number(1)
        self._dss_solution.StepSize(self._step_resolution)
        self._dss_solution.MaxControlIterations(settings.max_control_iterations)
        self._dss_solution.DblHour(self._hour + self._second / 3600.0)
        return

    def set_frequency(self, frequency):
        self._dss_solution.Frequency(frequency)
        return

    def get_frequency(self):
        return self._dss_solution.Frequency()

    def simulation_steps(self):
        seconds = (self._end_time - self._start_time).total_seconds()
        steps = math.ceil(seconds / self._step_resolution)
        return steps, self._start_time, self._end_time

    def get_opendss_time(self):
        return self._dss_solution.DblHour()

    def reset(self):
        self.set_mode("Dynamic")
        self._dss_solution.Hour(self._hour)
        self._dss_solution.Seconds(self._second)
        self._dss_solution.Number(1)
        self._dss_solution.StepSize(self._step_resolution)
        self._dss_solution.MaxControlIterations(self._settings.project.max_control_iterations)
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
        logger.debug("OpenDSS time [h] - " + str(self._dss_solution.DblHour()))
        logger.debug("Pydss datetime - " + str(self._time))
        return self._dss_solution.Converged()

    def re_solve(self):
        self._dss_solution.StepSize(0)
        self._dss_solution.SolveNoControl()
        return self._dss_solution.Converged()

    def solve(self):
        self._dss_solution.StepSize(0)
        self._dss_solution.Solve()
        return self._dss_solution.Converged()


Dynamic.setFrequency = Dynamic.set_frequency
Dynamic.getFrequency = Dynamic.get_frequency
Dynamic.SimulationSteps = Dynamic.simulation_steps
Dynamic.GetOpenDSSTime = Dynamic.get_opendss_time
Dynamic.SolveFor = Dynamic.solve_for
Dynamic.IncStep = Dynamic.inc_step
Dynamic.reSolve = Dynamic.re_solve
Dynamic.Solve = Dynamic.solve
