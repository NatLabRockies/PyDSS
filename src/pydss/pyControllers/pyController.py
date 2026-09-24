"""Deterministic registry for OpenMDAO controller components."""

from pydss.pyControllers.Controllers.DynamicVoltageSupport import DynamicVoltageSupport
from pydss.pyControllers.Controllers.FaultController import FaultController
from pydss.pyControllers.Controllers.GenController import GenController
from pydss.pyControllers.Controllers.MotorStall import MotorStall
from pydss.pyControllers.Controllers.MotorStallBackup import MotorStallBackup
from pydss.pyControllers.Controllers.MotorStallSimple import MotorStallSimple
from pydss.pyControllers.Controllers.PvController import PvController
from pydss.pyControllers.Controllers.PvDynamic import PvDynamic
from pydss.pyControllers.Controllers.PvFrequencyRideThru import PvFrequencyRideThru
from pydss.pyControllers.Controllers.PvVoltageRideThru import PvVoltageRideThru
from pydss.pyControllers.Controllers.SocketController import SocketController
from pydss.pyControllers.Controllers.StorageController import StorageController
from pydss.pyControllers.Controllers.ThermostaticLoad import ThermostaticLoad
from pydss.pyControllers.Controllers.xfmrController import xfmrController

ControllerTypes = {
    cls.__name__: cls for cls in (
        DynamicVoltageSupport, FaultController, GenController, MotorStall,
        MotorStallBackup, MotorStallSimple, PvController, PvDynamic,
        PvFrequencyRideThru, PvVoltageRideThru, SocketController,
        StorageController, ThermostaticLoad, xfmrController,
    )
}


def Create(controller_type, settings=None, *, element_name=""):
    """Create a controller component without an OpenDSS or solver dependency."""
    try:
        controller_class = ControllerTypes[controller_type]
    except KeyError as exc:
        raise ValueError(f"Unknown OpenMDAO controller component: {controller_type}") from exc
    return controller_class(settings=settings or {}, element_name=element_name)
