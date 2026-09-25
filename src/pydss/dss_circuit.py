import opendssdirect as dss

from pydss.dss_object_base import DssObjectBase


class DssCircuit(DssObjectBase):
    VARIABLE_OUTPUTS_BY_LABEL = {}
    VARIABLE_OUTPUTS_BY_LIST = ("AllBusMagPu",)
    VARIABLE_OUTPUTS_COMPLEX = (
        "LineLosses",
        "Losses",
        "SubstationLosses",
        "TotalPower",
    )

    def __init__(self, dss_instance=None):
        if dss_instance is None:
            dss_instance = dss
        name = dss_instance.Circuit.Name()
        full_name = "Circuit." + name
        self._Class = "Circuit"
        super(DssCircuit, self).__init__(dss_instance, name, full_name)

        ckt_elm_var_dict = dss_instance.Circuit.__dict__
        for key in ckt_elm_var_dict.keys():
            try:
                self._Variables[key] = getattr(dss_instance.Circuit, key)
            except Exception:
                self._Variables[key] = None

    def set_active_object(self):
        pass


globals()["dssCircuit"] = DssCircuit
