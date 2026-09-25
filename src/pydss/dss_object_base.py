import abc

from pydss.exceptions import InvalidParameter
from pydss.value_storage import ValueByLabel, ValueByList, ValueByNumber
import numpy as np


class DssObjectBase(abc.ABC):
    VARIABLE_OUTPUTS_BY_LABEL = {}
    VARIABLE_OUTPUTS_BY_LIST = ()
    VARIABLE_OUTPUTS_COMPLEX = ()

    def __init__(self, dss_instance, name, full_name):
        self._Name = name
        self._FullName = full_name
        self._Variables = {}
        self._dssInstance = dss_instance
        self._Enabled = True
        self._CachedValueStorage = {}

    @property
    def dss(self):
        return self._dssInstance

    @property
    def enabled(self):
        return self._Enabled

    @abc.abstractmethod
    def set_active_object(self):
        """Set the active DSS object."""

    def _get_labels(self, var_name):
        pass

    def data_length(self, var_name):
        self.set_active_object()
        if var_name in self._Variables:
            var_value = self.get_variable(var_name)
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

    def get_info(self):
        return self._Name

    def get_value(self, var_name, convert=False):
        self.set_active_object()
        if var_name in self._Variables:
            var_value = self.get_variable(var_name, convert=convert)
        else:
            var_value = np.nan
        return var_value

    def get_variable(self, var_name, convert=False):
        if var_name not in self._Variables:
            raise InvalidParameter(
                f"{var_name} is an invalid variable name for element {self._FullName}"
            )
        if self._dssInstance.Element.Name() != self._FullName:
            self.set_active_object()
        func = self._Variables[var_name]
        if func is None:
            raise InvalidParameter(f"get function for {self._FullName} / {var_name} is None")

        value = func()
        if not convert:
            return value

        if var_name in self.VARIABLE_OUTPUTS_BY_LABEL:
            info = self.VARIABLE_OUTPUTS_BY_LABEL[var_name]
            is_complex = info["is_complex"]
            units = info["units"]
            return ValueByLabel(self._FullName, var_name, value, self._Nodes, is_complex, units)
        elif var_name in self.VARIABLE_OUTPUTS_COMPLEX:
            assert isinstance(value, list) and len(value) == 2, str(value)
            value = complex(value[0], value[1])
        elif var_name in self.VARIABLE_OUTPUTS_BY_LIST:
            assert isinstance(value, list), str(value)
            labels = [f"_bus_index_{i}" for i in range(len(value))]
            return ValueByList(self._FullName, var_name, value, labels)
        return ValueByNumber(self._FullName, var_name, value)

    def update_value(self, var_name):

        cached_value = self._CachedValueStorage.get(var_name)
        if cached_value is None:
            cached_value = self.get_value(var_name, convert=True)
            self._CachedValueStorage[var_name] = cached_value
        else:
            value = self.get_value(var_name, convert=False)
            if (
                isinstance(cached_value, ValueByNumber)
                and var_name in self.VARIABLE_OUTPUTS_COMPLEX
            ):
                value = complex(value[0], value[1])
            cached_value.set_value_from_raw(value)

        return cached_value

    def get_variable_names(self):
        return self._Variables.keys()

    def in_variable_dict(self, var_name):
        return var_name in self._Variables

    def is_valid_attribute(self, var_name):
        return self.in_variable_dict(var_name)

    @property
    def full_name(self):
        return self._FullName

    @property
    def name(self):
        return self._Name

    def set_variable(self, var_name, value):
        if self._dssInstance.Element.Name() != self._FullName:
            self.set_active_object()
        if var_name not in self._Variables:
            raise InvalidParameter(f"invalid variable name {var_name}")

        return self._Variables[var_name](value)


globals()["dssObjectBase"] = DssObjectBase

setattr(DssObjectBase, "Enabled", DssObjectBase.enabled)
setattr(DssObjectBase, "FullName", DssObjectBase.full_name)
setattr(DssObjectBase, "Name", DssObjectBase.name)
setattr(DssObjectBase, "GetInfo", DssObjectBase.get_info)
setattr(DssObjectBase, "DataLength", DssObjectBase.data_length)
setattr(DssObjectBase, "SetActiveObject", DssObjectBase.set_active_object)
setattr(DssObjectBase, "GetValue", DssObjectBase.get_value)
setattr(DssObjectBase, "GetVariable", DssObjectBase.get_variable)
setattr(DssObjectBase, "UpdateValue", DssObjectBase.update_value)
setattr(DssObjectBase, "GetVariableNames", DssObjectBase.get_variable_names)
setattr(DssObjectBase, "inVariableDict", DssObjectBase.in_variable_dict)
setattr(DssObjectBase, "IsValidAttribute", DssObjectBase.is_valid_attribute)
setattr(DssObjectBase, "SetVariable", DssObjectBase.set_variable)
