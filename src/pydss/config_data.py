"""Converts Excel config files to TOML."""

from loguru import logger
import os

import numpy as np
import pandas as pd

from pydss.exceptions import InvalidParameter
from pydss.utils.utils import dump_data

def convert_config_data_to_toml(filename, name=None):
    """Converts an Excel config file to TOML.

    Parameters
    ----------
    filename : str
    name : str
        If not None, use this name instead of an auto-generated name.

    """
    dirname = os.path.dirname(filename)
    basename = os.path.splitext(os.path.basename(filename))[0]
    config_type = _get_config_type(basename)
    data = config_type["convert"](filename)
    if name is None:
        new_filename = os.path.join(dirname, basename + ".toml")
    else:
        new_filename = name
    dump_data(data, new_filename)
    logger.info("Converted %s to %s", filename, new_filename)
    return new_filename


def _get_config_type(basename):
    config_type = _CONFIG_TYPES.get(basename)
    if config_type is None:
        raise InvalidParameter(f"no ConfigType mapping for {basename}")

    return config_type


def _convert_controller(filename, name_field):
    df = pd.read_excel(filename, skiprows=[0,])
    controllers = df.to_dict(orient="records")
    data = {}
    for controller in controllers:
        name = controller.pop(name_field)
        data[name] = controller

    return data


def _convert_pv_controller(filename):
    return _convert_controller(filename, "Controlled PV")


def _convert_socket_controller(filename):
    return _convert_controller(filename, "Controlled Element")


def _convert_storage_controller(filename):
    return _convert_controller(filename, "Controlled Storage")


def _convert_xfmr_controller(filename):
    return _convert_controller(filename, "Controlled XFMR")

def _convert_motorstall(filename):
    return _convert_controller(filename, "Controlled Motor")

def _convert_PvVoltageRideThru(filename):
    return _convert_controller(filename, "Controlled PV")

def _convert_exports(filename, name_field):
    df = pd.read_excel(filename, skiprows=[0,])
    exports = {}
    for export in df.to_dict(orient="records"):
        cls = export.pop(name_field)
        if cls not in exports:
            exports[cls] = {"Publish": [], "NoPublish": []}
        values = [x for x in export.values() if x is not np.nan]
        if not values:
            raise InvalidParameter(f"export data has empty row: {export}")
        if export["Publish"]:
            exports[cls]["Publish"] += values[1:]
        else:
            exports[cls]["NoPublish"] += values[1:]

    return exports


def _convert_export_by_class(filename):
    return _convert_exports(filename, "Class")


def _convert_export_by_element(filename):
    return _convert_exports(filename, "Element")


def _convert_plot_config(filename):
    df = pd.read_excel(filename, skiprows=[0,])
    data = {}
    for item in df.to_dict(orient="records"):
        if "Filename" in item:
            name = item.pop("Filename")
        elif "FileName" in item:
            name = item.pop("FileName")
        else:
            assert False, str(item)
        item["plotType"] = os.path.splitext(os.path.basename(filename))[0]
        data[name] = item

    return data


def _convert_gis_overlay(df):
    pass


_CONFIG_TYPES = {
    "PvController": {
        "convert": _convert_pv_controller,
    },
    "SocketController": {
        "convert": _convert_socket_controller,
    },
    "StorageController": {
        "convert": _convert_storage_controller,
    },
    "MotorStall": {
        "convert": _convert_motorstall,
    },
    "PvVoltageRideThru": {
        "convert": _convert_PvVoltageRideThru,
    },
    "xfmrController": {
        "convert": _convert_xfmr_controller,
    },
    "ExportMode-byClass": {
        "convert": _convert_export_by_class,
    },
    "ExportMode-byElement": {
        "convert": _convert_export_by_element,
    },
    # TODO: this needs customization
    #"GIS overlay": {
    #    "convert": _convert_plot_config,
    #},
    "Histogram": {
        "convert": _convert_plot_config,
    },
    "Network layout": {
        "convert": _convert_plot_config,
    },
    "Sag plot": {
        "convert": _convert_plot_config,
    },
    "Time series": {
        "convert": _convert_plot_config,
    },
    "XY plot": {
        "convert": _convert_plot_config,
    },
}
