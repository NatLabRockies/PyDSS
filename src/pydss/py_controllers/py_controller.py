"""Deterministic registry for OpenMDAO controller components."""

from pydss.py_controllers.controllers.dynamic_voltage_support import DynamicVoltageSupport
from pydss.py_controllers.controllers.fault_controller import FaultController
from pydss.py_controllers.controllers.gen_controller import GenController
from pydss.py_controllers.controllers.motor_stall import MotorStall
from pydss.py_controllers.controllers.motor_stall_backup import MotorStallBackup
from pydss.py_controllers.controllers.motor_stall_simple import MotorStallSimple
from pydss.py_controllers.controllers.pv_controller import PvController
from pydss.py_controllers.controllers.pv_dynamic import PvDynamic
from pydss.py_controllers.controllers.pv_frequency_ride_thru import PvFrequencyRideThru
from pydss.py_controllers.controllers.pv_voltage_ride_thru import PvVoltageRideThru
from pydss.py_controllers.controllers.socket_controller import SocketController
from pydss.py_controllers.controllers.storage_controller import StorageController
from pydss.py_controllers.controllers.thermostatic_load import ThermostaticLoad
from pydss.py_controllers.controllers.xfmr_controller import XfmrController

controller_types = {
    cls.__name__: cls
    for cls in (
        DynamicVoltageSupport,
        FaultController,
        GenController,
        MotorStall,
        MotorStallBackup,
        MotorStallSimple,
        PvController,
        PvDynamic,
        PvFrequencyRideThru,
        PvVoltageRideThru,
        SocketController,
        StorageController,
        ThermostaticLoad,
        XfmrController,
    )
}


def create(controller_type, settings=None, *, element_name=""):
    """Create a controller component without an OpenDSS or solver dependency."""
    try:
        controller_class = controller_types[controller_type]
    except KeyError as exc:
        raise ValueError(f"Unknown OpenMDAO controller component: {controller_type}") from exc
    return controller_class(settings=settings or {}, element_name=element_name)


ControllerTypes = controller_types
Create = create
