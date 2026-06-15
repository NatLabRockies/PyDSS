
import abc
 
from pydss.exceptions import InvalidParameter
from pydss.value_storage import ValueByLabel, ValueByList, ValueByNumber
import numpy as np

class dssObjectBase(abc.ABC):

    VARIABLE_OUTPUTS_BY_LABEL = {}
    VARIABLE_OUTPUTS_BY_LIST = ()
    VARIABLE_OUTPUTS_COMPLEX = ()

    def __init__(self, dssInstance, name, fullName):
        self._Name = name
        self._FullName = fullName
        self._Variables = {}
        self._dssInstance = dssInstance
        self._Enabled = True
        self._CachedValueStorage = {}

    @property
    def dss(self):
        return self._dssInstance

    @property
    def Enabled(self):
        return self._Enabled

    @abc.abstractmethod
    def SetActiveObject(self):
        """Set the active DSS object."""

    def _get_labels(self, VarName):
        pass

    def DataLength(self, VarName):
        self.SetActiveObject()
        if VarName in self._Variables:
            VarValue = self.GetVariable(VarName)
        else:
            return 0, None
        if  isinstance(VarValue, list):
            return len(VarValue) , 'List'
        elif isinstance(VarValue, str):
            return 1, 'String'
        elif isinstance(VarValue, int or float or bool):
            return 1, 'Number'
        else:
            return 0, None

    def GetInfo(self):
        return self._Name

    def GetValue(self, VarName, convert=False):
        self.SetActiveObject()
        if VarName in self._Variables:
            VarValue = self.GetVariable(VarName, convert=convert)
        else:
            VarValue = np.nan
        return VarValue

    def GetVariable(self, VarName, convert=False):
        if VarName not in self._Variables:
            raise InvalidParameter(f'{VarName} is an invalid variable name for element {self._FullName}')
        if self._dssInstance.Element.Name() != self._FullName:
            self.SetActiveObject()
        func = self._Variables[VarName]
        if func is None:
            raise InvalidParameter(f"get function for {self._FullName} / {VarName} is None")

        value = func()
        if not convert:
            return value

        if VarName in self.VARIABLE_OUTPUTS_BY_LABEL:
            info = self.VARIABLE_OUTPUTS_BY_LABEL[VarName]
            is_complex = info["is_complex"]
            units = info["units"]
            return ValueByLabel(self._FullName, VarName, value, self._Nodes, is_complex, units)
        elif VarName in self.VARIABLE_OUTPUTS_COMPLEX:
            assert isinstance(value, list) and len(value) == 2, str(value)
            value = complex(value[0], value[1])
        elif VarName in self.VARIABLE_OUTPUTS_BY_LIST:
            assert isinstance(value, list), str(value)
            labels = [f"_bus_index_{i}" for i in range(len(value))]
            return ValueByList(self._FullName, VarName, value, labels)
        return ValueByNumber(self._FullName, VarName, value)

    def UpdateValue(self, VarName):
        
        cachedValue = self._CachedValueStorage.get(VarName)
        if cachedValue is None:
            cachedValue = self.GetValue(VarName, convert=True)
            self._CachedValueStorage[VarName] = cachedValue
        else:
            value = self.GetValue(VarName, convert=False)
            if isinstance(cachedValue, ValueByNumber) and VarName in self.VARIABLE_OUTPUTS_COMPLEX:
                value = complex(value[0], value[1])
            cachedValue.set_value_from_raw(value)

        return cachedValue

    def GetVariableNames(self):
        return self._Variables.keys()

    def inVariableDict(self, VarName):
        return VarName in self._Variables

    def IsValidAttribute(self, VarName):
        return self.inVariableDict(VarName)

    @property
    def FullName(self):
        return self._FullName

    @property
    def Name(self):
        return self._Name

    def SetVariable(self, VarName, Value):
        if self._dssInstance.Element.Name() != self._FullName:
            self.SetActiveObject()
        if VarName not in self._Variables:
            raise InvalidParameter(f"invalid variable name {VarName}")

        return self._Variables[VarName](Value)
