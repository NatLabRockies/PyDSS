from datetime import timedelta
import math
import abc

from loguru import logger

from pydss.simulation_input_models import ProjectModel


class SolverBase(abc.ABC):
    def __init__(self, dss_instance, settings: ProjectModel):

        self._settings = settings

        self._time = settings.start_time
        self._loadshape_init_time = settings.loadshape_start_time
        time_offset_days = (self._time - self._loadshape_init_time).days
        time_offset_seconds = (self._time - self._loadshape_init_time).seconds

        self._start_time = self._time
        self._end_time = self._time + timedelta(minutes=settings.simulation_duration_min)

        start_day = time_offset_days
        start_time_min = time_offset_seconds / 60.0
        step_resolution = settings.step_resolution_sec

        self.start_day = self._start_time.timetuple().tm_yday
        self.end_day = self._end_time.timetuple().tm_yday

        self._step_resolution = step_resolution
        self._dss_instance = dss_instance
        self._dss_solution = dss_instance.Solution

        self._hour = start_day * 24
        self._second = start_time_min * 60.0

        self.re_solve()
        logger.info("%s solver setup complete", settings.simulation_type)

    def set_frequency(self, frequency):
        self._dss_solution.Frequency(frequency)
        return

    def get_frequency(self):
        return self._dss_solution.Frequency()

    def simulation_steps(self):
        seconds = (self._end_time - self._start_time).total_seconds()
        steps = math.ceil(seconds / self._step_resolution)
        return steps, self._start_time, self._end_time

    def get_total_seconds(self):
        return (self._time - self._start_time).total_seconds()

    def get_datetime(self):
        return self._time

    def get_step_resolution_seconds(self):
        return self._step_resolution

    def get_step_size_sec(self):
        return self._step_resolution

    def get_mode(self):
        return self._dss_solution.ModeID()

    def set_mode(self, mode):
        return self._dss_instance.utils.run_command("Set Mode={}".format(mode))

    def get_opendss_time(self):
        return self._dss_solution.DblHour()

    def get_simulation_end_time(self):
        return self._end_time

    @property
    def max_iterations(self):
        return self._settings.max_control_iterations

    @abc.abstractmethod
    def solve_for(self, start_time, time_step):
        """Run a solve for a time step."""

    @abc.abstractmethod
    def reset(self):
        """Reset the solver"""

    @abc.abstractmethod
    def re_solve(self):
        """Run a SolveNoControl"""

    @abc.abstractmethod
    def solve(self):
        """Run a solve."""

    @abc.abstractmethod
    def inc_step(self):
        """Increment the simulation time step"""


solver_base = SolverBase
SolverBase.setFrequency = SolverBase.set_frequency
SolverBase.getFrequency = SolverBase.get_frequency
SolverBase.SimulationSteps = SolverBase.simulation_steps
SolverBase.GetTotalSeconds = SolverBase.get_total_seconds
SolverBase.GetDateTime = SolverBase.get_datetime
SolverBase.GetStepResolutionSeconds = SolverBase.get_step_resolution_seconds
SolverBase.GetStepSizeSec = SolverBase.get_step_size_sec
SolverBase.getMode = SolverBase.get_mode
SolverBase.setMode = SolverBase.set_mode
SolverBase.GetOpenDSSTime = SolverBase.get_opendss_time
SolverBase.MaxIterations = SolverBase.max_iterations
SolverBase.SolveFor = SolverBase.solve_for
SolverBase.reSolve = SolverBase.re_solve
SolverBase.Solve = SolverBase.solve
SolverBase.IncStep = SolverBase.inc_step
