from loguru import logger
import opendssdirect as dss

from pydss.common import SimulationType
from pydss.exceptions import InvalidParameter
from pydss.modes.Dynamic import Dynamic
from pydss.modes.Snapshot import Snapshot
from pydss.modes.QSTS import QSTS
from pydss.simulation_input_models import ProjectModel, SimulationSettingsModel


def GetSolver(settings: SimulationSettingsModel, dssInstance):
    # logger.info('Setting solver to %s mode.', settings.project.simulation_type.value)
    logger.info(f'Setting solver to {settings.project.simulation_type.value} mode.')
    return get_solver_from_simulation_type(settings.project)


def get_solver_from_simulation_type(settings: ProjectModel):
    """Return a solver from the simulation type."""
    if settings.simulation_type == SimulationType.SNAPSHOT:
        return Snapshot(dssInstance=dss, settings=settings)
    elif settings.simulation_type == SimulationType.QSTS:
        return QSTS(dssInstance=dss, settings=settings)
    elif settings.simulation_type == SimulationType.DYNAMIC:
        return Dynamic(dssInstance=dss, settings=settings)
    raise InvalidParameter(f"{settings.simulation_type} does not have a supported solver")
