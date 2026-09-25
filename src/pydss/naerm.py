# Kapil Duwadi
PYDSS_DICT = {
    "CurrentsMagAng": "vector",
    "Currents": "vector",
    "RatedCurrent": "double",
    "EmergAmps": "double",
    "NormalAmps": "double",
    "normamps": "double",
    "Losses": "vector",
    "PhaseLosses": "vector",
    "Powers": "vector",
    "TotalPower": "vector",
    "LineLosses": "vector",
    "SubstationLosses": "vector",
    "kV": "double",
    "kVARated": "double",
    "kvar": "double",
    "kW": "double",
    "kVABase": "double",
    "kWh": "double",
    "puVmagAngle": "vector",
    "VoltagesMagAng": "vector",
    "VMagAngle": "vector",
    "Voltages": "vector",
    "Vmaxpu": "double",
    "Vminpu": "double",
    "Frequency": "double",
    "Taps": "vector",
    "%stored": "double",
    "Distance": "double",
}


ASSETTYPEMAPDICT = {
    "Buses": "bus",
    "Lines": "line",
    "Loads": "load",
    "PVSystems": "pv",
    "Transformers": "trans",
    "Faults": "fault",
    "Storages": "storage",
    "Circuit": "circuit",
}

PROPERTYMAPDICT = {
    "CurrentMagAng": ["current double", "current_angle double"],
    "TotalPower": ["power_real double", "power_imag double"],
}

PARAMETERNAME2INDEX = {"power_real": 0, "power_imag": 1}


def isnaerm(name):

    try:
        if len(name.split("/")) == 5:
            return True
        else:
            return False

    except Exception:
        return False


def get_naerm_value(value, naerm_name):

    federate_name, asset_type, asset_name, parameter_name, parameter_unit = naerm_name.split("/")
    if isinstance(value, list):
        try:
            value = value[PARAMETERNAME2INDEX[parameter_name]]
            return value
        except Exception:
            return "Failed"

    else:
        return value


def pydss_to_naerm(pydssname):

    try:
        fed_name, class_name, object_name, ppty_name = pydssname.split(".")
        asset_type = ASSETTYPEMAPDICT[class_name]
        parameter_name = PROPERTYMAPDICT[ppty_name]
        if isinstance(parameter_name, list):
            naerm_name = [
                f"{fed_name}/{asset_type}/{object_name}/{param.split(' ')[0]}/{param.split(' ')[1]}"
                for param in parameter_name
            ]

        else:
            naerm_name = f"{fed_name}/{asset_type}/{object_name}/{parameter_name.split(' ')[0]}/{parameter_name.split(' ')[1]}"
        return naerm_name

    except Exception:
        return "Failed"


def naerm_to_pydss(naerm_name):

    try:
        federate_name, asset_type, asset_name, parameter_name, parameter_unit = naerm_name.split(
            "/"
        )
        for keys, values in ASSETTYPEMAPDICT.items():
            if values == asset_type:
                class_name = keys
                break

        for keys, values in PROPERTYMAPDICT.items():
            if isinstance(values, list):
                if parameter_name + " " + parameter_unit in values:
                    ppty_name = keys
                    break
            else:
                if parameter_name == values:
                    break

        return f"{federate_name}.{class_name}.{asset_name}.{ppty_name}"

    except Exception:
        return "Failed"


if __name__ == "__main__":
    name = "pydss_x/circuit/heco19021/power_real/double"
    # print(get_naerm_value([34,45],'pydss_x/circuit/heco19021/power_imag/double' ))
