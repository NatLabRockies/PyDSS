from loguru import logger
import opendssdirect as dss

from pydss.common import SimulationType
from pydss.exceptions import InvalidParameter
from pydss.modes.dynamic import Dynamic
from pydss.modes.snapshot import Snapshot
from pydss.modes.qsts import QSTS
from pydss.simulation_input_models import ProjectModel, SimulationSettingsModel


def get_solver(settings: SimulationSettingsModel, dss_instance):
    logger.info("Setting solver to %s mode.", settings.project.simulation_type.value)
    return get_solver_from_simulation_type(settings.project)


def get_solver_from_simulation_type(settings: ProjectModel):
    """Return a solver from the simulation type."""
    if settings.simulation_type == SimulationType.SNAPSHOT:
        return Snapshot(dss_instance=dss, settings=settings)
    elif settings.simulation_type == SimulationType.QSTS:
        return QSTS(dss_instance=dss, settings=settings)
    elif settings.simulation_type == SimulationType.DYNAMIC:
        return Dynamic(dss_instance=dss, settings=settings)
    raise InvalidParameter(f"{settings.simulation_type} does not have a supported solver")


globals()["GetSolver"] = get_solver
