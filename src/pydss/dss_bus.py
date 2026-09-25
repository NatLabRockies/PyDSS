import opendssdirect as dss

from pydss.dss_object_base import DssObjectBase


class DssBus(DssObjectBase):
    VARIABLE_OUTPUTS_BY_LABEL = {
        "PuVoltage": {"is_complex": True, "units": ["[pu]"]},
        "SeqVoltages": {"is_complex": False, "units": ["[kV]", "[Deg]"]},
        "CplxSeqVoltages": {"is_complex": True, "units": ["[kV]"]},
        "VMagAngle": {"is_complex": False, "units": ["[kV]", "[Deg]"]},
        "Voc": {"is_complex": True, "units": ["[kV]"]},
        "Voltages": {"is_complex": True, "units": ["[kV]"]},
        "puVmagAngle": {"is_complex": False, "units": ["[pu]", "[Deg]"]},
        "Isc": {"is_complex": True, "units": ["[Amps]"]},
    }
    VARIABLE_OUTPUTS_COMPLEX = ()

    def __init__(self, dss_instance=None):
        if dss_instance is None:
            dss_instance = dss
        name = dss_instance.Bus.Name()
        super(DssBus, self).__init__(dss_instance, name, name)
        self._Index = None
        self.XY = None
        self._Class = "Bus"
        #  self._Nodes is nested in a list to be consistent with DssElement._Nodes
        self._Nodes = [dss_instance.Bus.Nodes()]
        self._NumTerminals = 1
        self._NumConductors = len(dss_instance.Bus.Nodes())
        self.Distance = dss_instance.Bus.Distance()
        bus_var_dict = dss_instance.Bus.__dict__
        for key in bus_var_dict.keys():
            try:
                self._Variables[key] = getattr(dss_instance.Bus, key)
            except Exception:
                self._Variables[key] = None
        if self.get_variable("X") is not None:
            self.XY = [self.get_variable("X"), self.get_variable("Y")]
        else:
            self.XY = [0, 0]

    @property
    def num_conductors(self):
        return self._NumConductors

    @property
    def num_phases(self):
        return len(self._Nodes)

    @property
    def phases(self):
        return self._Nodes[:]

    def set_active_object(self):
        try:
            if self._dssInstance.Bus.Name() != self._Name:
                self._dssInstance.Circuit.SetActiveBus(self._Name)
            return 1
        except Exception:
            return 0


globals()["dssBus"] = DssBus

setattr(DssBus, "NumConductors", DssBus.num_conductors)
setattr(DssBus, "NumPhases", DssBus.num_phases)
setattr(DssBus, "Phases", DssBus.phases)
