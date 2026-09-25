import ast

from opendssdirect import DSSException

from pydss.dss_bus import DssBus
from pydss.dss_object_base import DssObjectBase
from pydss.exceptions import InvalidParameter
from pydss.value_storage import ValueByNumber


class DssElement(DssObjectBase):
    VARIABLE_OUTPUTS_BY_LABEL = {
        "Currents": {"is_complex": True, "units": ["[Amps]"]},
        "CurrentsMagAng": {"is_complex": False, "units": ["[Amps]", "[Deg]"]},
        "Powers": {"is_complex": True, "units": ["[kVA]"]},
        "Voltages": {"is_complex": True, "units": ["[kV]"]},
        "VoltagesMagAng": {"is_complex": False, "units": ["[kV]", "[Deg]"]},
        "CplxSeqCurrents": {"is_complex": True, "units": ["[Amps]"]},
        "SeqCurrents": {"is_complex": False, "units": ["[Amps]", "[Deg]"]},
        "SeqPowers": {"is_complex": False, "units": ["[kVA]", "[Deg]"]},
    }

    VARIABLE_OUTPUTS_COMPLEX = ("Losses",)

    _MAX_CONDUCTORS = 4

    def __init__(self, dss_instance):
        full_name = dss_instance.Element.Name()
        if dss_instance.CktElement.Name() != full_name:
            raise Exception(f"name mismatch {dss_instance.CktElement.Name()} {full_name}")

        self._Class, name = full_name.split(".", 1)
        super(DssElement, self).__init__(dss_instance, name, full_name)
        self._Enabled = dss_instance.CktElement.Enabled()
        if not self._Enabled:
            return

        self._Parameters = {}
        self._NumTerminals = dss_instance.CktElement.NumTerminals()
        self._NumConductors = dss_instance.CktElement.NumConductors()

        assert self._NumConductors <= self._MAX_CONDUCTORS, str(self._NumConductors)
        self._NumPhases = dss_instance.CktElement.NumPhases()

        n = self._NumConductors
        nodes = dss_instance.CktElement.NodeOrder()
        self._Nodes = [nodes[i * n : (i + 1) * n] for i in range((len(nodes) + n - 1) // n)]

        assert len(nodes) == self._NumTerminals * self._NumConductors, (
            f"{self._Nodes} {self._NumTerminals} {self._NumConductors}"
        )

        self._dssInstance = dss_instance

        properties_names = self._dssInstance.Element.AllPropertyNames()
        as_ = range(len(properties_names))
        for i, ppt_name in zip(as_, properties_names):
            self._Parameters[ppt_name] = str(i)

        ckt_elm_var_dict = dss_instance.CktElement.__dict__
        try:
            for var_name in dss_instance.CktElement.AllVariableNames():
                ckt_elm_var_dict[var_name] = None
        except DSSException as e:
            # Prior to OpenDSSDirect.py v0.8.0 this returned an empty list for non-PC elements.
            # v0.8.0 and later raises an exception. Ignore the error.
            if e.args[1] != "The active circuit element is not a PC Element":
                raise

        for key in ckt_elm_var_dict.keys():
            try:
                self._Variables[key] = getattr(dss_instance.CktElement, key)
            except Exception:
                self._Variables[key] = None
        self.Bus = dss_instance.CktElement.BusNames()
        self.BusCount = len(self.Bus)
        self.sBus = []
        for bus_name in self.Bus:
            self._dssInstance.Circuit.SetActiveBus(bus_name)
            self.sBus.append(DssBus(self._dssInstance))

    def get_info(self):
        return self._Class, self._Name

    def is_valid_attribute(self, var_name):
        # Overridden from base because DssElement has Parameters.
        if var_name in self._Variables:
            return True
        elif var_name in self._Parameters:
            return True
        else:
            return False

    def data_length(self, var_name):
        if var_name in self._Variables:
            var_value = self.get_variable(var_name)
        elif var_name in self._Parameters:
            var_value = self.get_parameter(var_name)
        else:
            return 0, None

        if isinstance(var_value, list):
            return len(var_value), "List"
        elif isinstance(var_value, str):
            return 1, "String"
        elif isinstance(var_value, int or float or bool):
            return 1, "Number"
        else:
            return 0, None

    def get_value(self, var_name, convert=False):
        if self._dssInstance.Element.Name() != self._FullName:
            self.set_active_object()
        if var_name in self._Variables:
            var_value = self.get_variable(var_name, convert=convert)
        elif var_name in self._Parameters:
            var_value = self.get_parameter(var_name)
            if convert:
                var_value = ValueByNumber(self._FullName, var_name, var_value)
        else:
            return None
        return var_value

    def set_active_object(self):
        self._dssInstance.Circuit.SetActiveElement(self._FullName)
        if self._dssInstance.CktElement.Name() != self._dssInstance.Element.Name():
            raise InvalidParameter("Object is not a circuit element")

    def set_parameter(self, param, value):
        reply = self._dssInstance.utils.run_command(
            self._FullName + "." + param + " = " + str(value)
        )
        if reply != "":
            raise Exception(f"SetParameter failed: {reply}")
        return self.get_parameter(param)

    def get_parameter(self, param):
        if self._dssInstance.Element.Name() != self._FullName:
            self._dssInstance.Circuit.SetActiveElement(self._FullName)
        if self._dssInstance.Element.Name() == self._FullName:
            # This always returns a string.
            # The real value could be a number, a list of numbers, or a string.
            x = self._dssInstance.Properties.Value(param)
            try:
                return float(x)
            except ValueError:
                try:
                    return ast.literal_eval(x)
                except (SyntaxError, ValueError):
                    return x
        else:
            return None

    @property
    def conductors(self):
        letters = "ABCN"
        return [letters[i] for i in range(self._NumConductors)]

    @property
    def conductor_by_terminal(self):
        return [f"{j}{i}" for i in self.conductors for j in self.terminals]

    @property
    def node_order(self):
        return self._NodeOrder[:]

    @property
    def num_phases(self):
        return self._NumPhases

    @property
    def num_conductors(self):
        return self._NumConductors

    @property
    def num_terminals(self):
        return self._NumTerminals

    @property
    def terminals(self):
        return list(range(1, self._NumTerminals + 1))


globals()["dssElement"] = DssElement

setattr(DssElement, "SetParameter", DssElement.set_parameter)
setattr(DssElement, "GetParameter", DssElement.get_parameter)
setattr(DssElement, "Conductors", DssElement.conductors)
setattr(DssElement, "ConductorByTerminal", DssElement.conductor_by_terminal)
setattr(DssElement, "NodeOrder", DssElement.node_order)
setattr(DssElement, "NumPhases", DssElement.num_phases)
setattr(DssElement, "NumConductors", DssElement.num_conductors)
setattr(DssElement, "NumTerminals", DssElement.num_terminals)
setattr(DssElement, "Terminals", DssElement.terminals)
