import re

import opendssdirect as dss
from loguru import logger


def check_redirect(file_name):
    """Runs redirect command for dss file
    And checks for exception

    Parameters
    ----------
    file_name : str
        dss file to be redirected

    Raises
    -------
    Exception
        Raised if the command fails

    """
    logger.debug(f"Redirecting DSS file: {file_name}")
    result = dss.run_command(f"Redirect {file_name}")
    if result != "":
        raise Exception(f"Redirect failed for {file_name}, message: {result}")


def read_pv_systems_from_dss_file(filename):
    """Return PVSystem names specified in OpenDSS deployment file.

    Parameters
    ----------
    filename : str

    Returns
    -------
    list

    """
    pv_systems = []
    """
    New PVSystem.pv_1114018 bus1=133294_xfmr.1.2 phases=2
    """
    regex = re.compile(r"New (PVSystem\.)([\S]+)\s", re.I)

    with open(filename) as fp_in:
        for line in fp_in:
            match = regex.search(line)
            if match:
                pv_systems.append(match.group(1) + match.group(2).lower())

    logger.debug("Found pv_systems=%s in %s", pv_systems, filename)
    return pv_systems


def get_load_shape_resolution_secs():
    def func():
        if dss.LoadShape.Name() == "default":
            return None
        return dss.LoadShape.SInterval()

    res = [x for x in iter_elements(dss.LoadShape, func) if x is not None]
    if len(set(res)) != 1:
        return None
        # raise InvalidConfiguration(
        #     f"SInterval for all LoadShapes must be the same: {res}"
        # )

    return res[0]


def get_node_names_by_type(kv_base_threshold=1.0):
    """Return a mapping of node type to node names.

    Parameters
    ----------
    kv_base_threshold : float
        Voltage to use as threshold for identifying primary vs secondary

    Returns
    -------
    dict
        keys are "primaries" or "secondaries"
        values are a list of node names

    """
    names_by_type = {"primaries": [], "secondaries": []}
    for i, name in enumerate(dss.Circuit.AllNodeNames()):
        dss.Circuit.SetActiveBus(name)
        kv_base = dss.Bus.kVBase()
        if kv_base > kv_base_threshold:
            names_by_type["primaries"].append(name)
        else:
            names_by_type["secondaries"].append(name)

    return names_by_type


def list_element_names_by_class_name(class_name):
    """Return a list of names of all elements of a given element class.

    Parameters
    ----------
    class_name : str
        Subclass of opendssdirect.CktElement

    Returns
    -------
    list

    Examples
    --------
    >>> names = list_element_names_by_class("Loads")

    """
    if class_name == "Buses":
        return dss.Circuit.AllBusNames()
    elif class_name == "Nodes":
        return dss.Circuit.AllNodeNames()

    dss.Basic.SetActiveClass(class_name)
    return dss.ActiveClass.AllNames()


def list_element_names_by_class(element_class):
    """Return a list of names of all elements of a given element class.

    Parameters
    ----------
    element_class : class
        Subclass of opendssdirect.CktElement

    Returns
    -------
    list

    Examples
    --------
    >>> import opendssdirect as dss

    >>> names = list_element_names_by_class(dss.PVsystems)

    """
    if element_class is dss.PVsystems:
        class_name = "PVSystem"
    else:
        class_name = element_class.__name__.split(".")[1]
        # TODO: confirm that this covers everything.
        if class_name.endswith("s"):
            class_name = class_name[:-1]

    return [f"{class_name}.{x}" for x in iter_elements(element_class, element_class.Name)]


def iter_elements(element_class, element_func):
    """Yield the return of element_func for each element of type element_class.

    Parameters
    ----------
    element_class : class
        Subclass of opendssdirect.CktElement
    element_func : function
        Function to run on each element

    Yields
    ------
    Return of element_func

    Examples
    --------
    >>> import opendssdirect as dss

    >>> def get_reg_control_info():
        return {
            "name": dss.RegControls.Name(),
            "enabled": dss.CktElement.Enabled(),
            "transformer": dss.RegControls.Transformer(),
        }

    >>> for reg_control in iter_elements(opendssdirect.RegControls, get_reg_control_info):
        print(reg_control["name"])

    """
    flag = element_class.First()
    while flag > 0:
        yield element_func()
        flag = element_class.Next()
