
import enum
import os
from collections import namedtuple

import pydss
from pydss.utils.utils import load_data

DATE_FORMAT = '%Y-%m-%d %H:%M:%S.%f' # '%Y-%m-%d %H:%M:%S.%f', "%m/%d/%Y %H:%M:%S"
TIME_FORMAT = '%H:%M:%S'

PLOTS_FILENAME = "plots.toml"
SIMULATION_SETTINGS_FILENAME = "simulation.toml"
RUN_SIMULATION_FILENAME = "simulation-run.toml"
MONTE_CARLO_SETTINGS_FILENAME = "MonteCarloSettings.toml"
OPENDSS_MASTER_FILENAME = "Master.dss"
SUBSCRIPTIONS_FILENAME = "Subscriptions.toml"
PROJECT_TAR = "project.tar"
PROJECT_ZIP = "project.zip"
PROFILE_MAPPING = "mapping.toml"
PROFILE_SRC_H5 = "profiles.h5"
PV_LOAD_SHAPE_FILENAME = "pv_load_shape_data.h5"
PV_PROFILES_FILENAME = "pv_profiles.json"
NODE_NAMES_BY_TYPE_FILENAME = "node_names_by_type.json"
INTEGER_NAN = -9999

class ControllerType(enum.Enum):
    FAULT_CONTROLLER = "FaultController"
    GENERATOR_CONTROLLER = "GenController"
    MOTOR_STALL = "MotorStall"
    MOTOR_STALL_SIMPLE = "MotorStallSimple"
    PV_CONTROLLER = "PvController"
    PV_DYNAMIC = "PvDynamic"
    PV_FREQUENCY_RIDETHROUGH = "PvFrequencyRideThru"
    PV_VOLTAGE_RIDETHROUGH = "PvVoltageRideThru"
    SOCKET_CONTROLLER = "SocketController"
    STORAGE_CONTROLLER = "StorageController"
    THERMOSTATIC_LOAD_CONTROLLER = "ThermostaticLoad"
    XMFR_CONTROLLER = "xmfrController"

CONTROLLER_TYPES = tuple(x.value for x in ControllerType)
CONFIG_EXT = ".toml"

class ExportMode(enum.Enum):
    BY_CLASS = "ExportMode-byClass"
    BY_ELEMENT = "ExportMode-byElement"
    SUBSCRIPTIONS = 'Subscriptions'
    EXPORTS = "Exports"

def filename_from_enum(obj):
    return obj.value + CONFIG_EXT

FAULT_CONTROLLER_FILENAME = filename_from_enum(ControllerType.FAULT_CONTROLLER)
GENERATOR_CONTROLLER_FILENAME = filename_from_enum(ControllerType.GENERATOR_CONTROLLER)
MOTOR_STALL_FILENAME = filename_from_enum(ControllerType.MOTOR_STALL)
MOTOR_STALL_SIMPLE_FILENAME = filename_from_enum(ControllerType.MOTOR_STALL_SIMPLE)
PV_CONTROLLER_FILENAME = filename_from_enum(ControllerType.PV_CONTROLLER)
PV_DYNAMIC_FILENAME = filename_from_enum(ControllerType.PV_DYNAMIC)
PV_FREQUENCY_RIDETHROUGH_FILENAME = filename_from_enum(ControllerType.PV_FREQUENCY_RIDETHROUGH)
PV_VOLTAGE_RIDETHROUGH_FILENAME = filename_from_enum(ControllerType.PV_VOLTAGE_RIDETHROUGH)
SOCKET_CONTROLLER_FILENAME = filename_from_enum(ControllerType.SOCKET_CONTROLLER)
STORAGE_CONTROLLER_FILENAME = filename_from_enum(ControllerType.STORAGE_CONTROLLER)
THERMOSTATIC_LOAD_CONTROLLER_FILENAME = filename_from_enum(ControllerType.THERMOSTATIC_LOAD_CONTROLLER)
XMFR_CONTROLLER_FILENAME = filename_from_enum(ControllerType.XMFR_CONTROLLER)

EXPORT_BY_CLASS_FILENAME = filename_from_enum(ExportMode.BY_CLASS)
EXPORT_BY_ELEMENT_FILENAME = filename_from_enum(ExportMode.BY_ELEMENT)
EXPORTS_FILENAME = filename_from_enum(ExportMode.EXPORTS)

DEFAULT_FAULT_CONTROLLER_CONFIG_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    "pyControllerList",
    FAULT_CONTROLLER_FILENAME,
)
DEFAULT_GENERATOR_CONTROLLER_CONFIG_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    "pyControllerList",
    GENERATOR_CONTROLLER_FILENAME,
)
DEFAULT_MOTOR_STALL_CONTROLLER_CONFIG_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    "pyControllerList",
    MOTOR_STALL_FILENAME,
)
DEFAULT_PV_CONTROLLER_CONFIG_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    "pyControllerList",
    PV_CONTROLLER_FILENAME,
)
DEFAULT_PV_DYNAMIC_CONTROLLER_CONFIG_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    "pyControllerList",
    PV_DYNAMIC_FILENAME,
)
DEFAULT_PV_FREQUENCY_RIDETHROUGH_CONTROLLER_CONFIG_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    "pyControllerList",
    PV_FREQUENCY_RIDETHROUGH_FILENAME,
)
DEFAULT_PV_VOLTAGE_RIDETHROUGH_CONTROLLER_CONFIG_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    "pyControllerList",
    PV_VOLTAGE_RIDETHROUGH_FILENAME,
)
DEFAULT_SOCKET_CONTROLLER_CONFIG_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    "pyControllerList",
    SOCKET_CONTROLLER_FILENAME,
)
DEFAULT_STORAGE_CONTROLLER_CONFIG_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    "pyControllerList",
    STORAGE_CONTROLLER_FILENAME,
)
DEFAULT_THERMOSTATIC_LOAD_CONTROLLER_CONFIG_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    "pyControllerList",
    THERMOSTATIC_LOAD_CONTROLLER_FILENAME,
)
DEFAULT_XMFR_CONTROLLER_CONFIG_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    "pyControllerList",
    XMFR_CONTROLLER_FILENAME,
)

DEFAULT_SUBSCRIPTIONS_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    "ExportLists",
    SUBSCRIPTIONS_FILENAME,
)
DEFAULT_SIMULATION_SETTINGS_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    SIMULATION_SETTINGS_FILENAME,
)

DEFAULT_PLOT_SETTINGS_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    PLOTS_FILENAME
)
DEFAULT_EXPORT_BY_CLASS_SETTINGS_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    "ExportLists",
    EXPORT_BY_CLASS_FILENAME,
)
DEFAULT_EXPORT_BY_ELEMENT_SETTINGS_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    "ExportLists",
    EXPORTS_FILENAME,
)
DEFAULT_EXPORTS_SETTINGS_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    "ExportLists",
    EXPORT_BY_ELEMENT_FILENAME,
)
DEFAULT_MONTE_CARLO_SETTINGS_FILE = os.path.join(
    os.path.dirname(getattr(pydss, "__path__")[0]),
    "pydss",
    "defaults",
    "Monte_Carlo",
    MONTE_CARLO_SETTINGS_FILENAME,
)
class ControlMode(enum.Enum):
    """Supported control modes"""
    STATIC = "Static"
    TIME = "Time"
class DataConversion(enum.Enum):
    NONE = "none"
    ABS = "abs"
    ABS_SUM = "abs_sum"
    SUM = "sum"
    SUM_REAL = "sum_real"
    SUM_ABS_REAL = "sum_abs_real"
class DatasetPropertyType(enum.Enum):
    PER_TIME_POINT = "per_time_point"  # data is stored at every time point
    FILTERED = "filtered"  # data is stored after being filtered
    METADATA = "metadata"  # metadata for another dataset
    TIME_STEP = "time_step"  # data are time indices, tied to FILTERED
    VALUE = "value"  # Only a single value is written for each element
class FileFormat(enum.Enum):
    """Supported file formats"""
    CSV = "csv"
    HDF5 = "h5"


class LimitsFilter(enum.Enum):
    INSIDE = "inside"
    OUTSIDE = "outside"


class LoggingLevel(enum.Enum):
    """Supported logging levels"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ReportGranularity(enum.Enum):
    """Specifies the granularity on which data is collected."""
    PER_ELEMENT_PER_TIME_POINT = "per_element_per_time_point"
    PER_ELEMENT_TOTAL = "per_element_total"
    ALL_ELEMENTS_PER_TIME_POINT = "all_elements_per_time_point"
    ALL_ELEMENTS_TOTAL = "all_elements_total"


class SimulationType(enum.Enum):
    """Supported simulation types"""
    DYNAMIC = "dynamic"
    QSTS = "qsts"
    SNAPSHOT = "snapshot"


class SnapshotTimePointSelectionMode(enum.Enum):
    """Defines methods by which snapshot time points can be calculated."""

    MAX_PV_LOAD_RATIO = "max_pv_load_ratio"
    MAX_LOAD = "max_load"
    DAYTIME_MIN_LOAD = "daytime_min_load"
    MAX_PV_MINUS_LOAD = "pv_minus_load"
    NONE = "none"


class StoreValuesType(enum.Enum):
    ALL = "all"
    CHANGE_COUNT = "change_count"
    MAX = "max"
    MIN = "min"
    MOVING_AVERAGE = "moving_average"
    MOVING_AVERAGE_MAX = "moving_average_max"
    SUM = "sum"


MinMax = namedtuple("MinMax", "min, max")
