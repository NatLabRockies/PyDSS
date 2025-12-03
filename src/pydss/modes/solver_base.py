from datetime import timedelta
import math
import abc

from loguru import logger

from pydss.common import DATE_FORMAT
from pydss.simulation_input_models import ProjectModel

class solver_base(abc.ABC):
    def __init__(self, dssInstance, settings: ProjectModel):

        self._settings = settings

        self._Time = settings.start_time
        self._Loadshape_init_time = settings.loadshape_start_time
        time_offset_days = (self._Time - self._Loadshape_init_time).days
        time_offset_seconds = (self._Time - self._Loadshape_init_time).seconds

        self._StartTime = self._Time
        self._EndTime = self._Time + timedelta(minutes=settings.simulation_duration_min)

        StartDay = time_offset_days
        StartTimeMin = time_offset_seconds / 60.0
        sStepResolution = settings.step_resolution_sec/3

        self.StartDay = self._StartTime.timetuple().tm_yday
        self.EndDay = self._EndTime.timetuple().tm_yday

        self._sStepRes = sStepResolution
        self._dssInstance = dssInstance
        self._dssSolution = dssInstance.Solution

        self._Hour = StartDay * 24
        self._Second = StartTimeMin * 60.0

        #self._dssSolution.DblHour()
        self.reSolve()
        logger.info(f"{settings.simulation_type} solver setup complete")

    def setFrequency(self, frequency):
        self._dssSolution.Frequency(frequency)
        return

    def getFrequency(self):
        return self._dssSolution.Frequency()

    def SimulationSteps(self):
        Seconds = (self._EndTime - self._StartTime).total_seconds()
        Steps = math.ceil(Seconds / self._sStepRes)
        return Steps, self._StartTime, self._EndTime

    def GetTotalSeconds(self):
        return (self._Time - self._StartTime).total_seconds()

    def GetDateTime(self):
        return self._Time

    def GetStepResolutionSeconds(self):
        return self._sStepRes

    def GetStepSizeSec(self):
        return self._sStepRes

    def getMode(self):
        return self._dssSolution.ModeID()

    def setMode(self, mode):
        return self._dssInstance.utils.run_command('Set Mode={}'.format(mode))

    def GetOpenDSSTime(self):
        return self._dssSolution.DblHour()

    def get_simulation_end_time(self):
        return self._EndTime

    @property
    def MaxIterations(self):
        return self._settings.max_control_iterations

    @abc.abstractmethod
    def SolveFor(self, mStartTime, mTimeStep):
        """Run SolveFor"""

    @abc.abstractmethod
    def reset(self):
        """Reset the solver"""

    @abc.abstractmethod
    def reSolve(self):
        """Run a SolveNoControl"""

    @abc.abstractmethod
    def Solve(self):
        """Run a Solve"""

    @abc.abstractmethod
    def IncStep(self):
        """Increment the simulation time step"""
