import ast
from loguru import logger
from opendssdirect import DSSException

from pydss.dssBus import dssBus
from pydss.dssObjectBase import dssObjectBase
from pydss.exceptions import InvalidParameter
from pydss.value_storage import ValueByNumber


class dssElement(dssObjectBase):

    VARIABLE_OUTPUTS_BY_LABEL = {
        "Currents": {
            "is_complex": True,
            "units": ['[Amps]']
        },
        "CurrentsMagAng": {
            "is_complex": False,
            "units" : ['[Amps]', '[Deg]']
        },
        "Powers": {
            "is_complex": True,
            "units": ['[kVA]']
        },
        "Voltages": {
            "is_complex": True,
            "units": ['[kV]']
        },
        'VoltagesMagAng': {
            "is_complex": False,
            "units": ['[kV]', '[Deg]']
        },
        'CplxSeqCurrents': {
            "is_complex": True,
            "units": ['[Amps]']
        },
        'SeqCurrents': {
            "is_complex": False,
            "units": ['[Amps]', '[Deg]']
        },
        'SeqPowers': {
            "is_complex": False,
            "units": ['[kVA]', '[Deg]']
        }
    }

    VARIABLE_OUTPUTS_COMPLEX = (
        "Losses",
    )

    _MAX_CONDUCTORS = 4

    def __init__(self, dssInstance):
        fullName = dssInstance.Element.Name()
        if dssInstance.CktElement.Name() != fullName:
            raise Exception(f"name mismatch {dssInstance.CktElement.Name()} {fullName}")

        self._Class, name = fullName.split('.', 1)
        super(dssElement, self).__init__(dssInstance, name, fullName)
        self._Enabled = dssInstance.CktElement.Enabled()
        if not self._Enabled:
            logger.debug(f"Element isn't defined: {fullName}")
            return
        self._Parameters = {}
        logger.debug(fullName)
        self._NumTerminals = dssInstance.CktElement.NumTerminals()
        self._NumConductors = dssInstance.CktElement.NumConductors()

        assert self._NumConductors <= self._MAX_CONDUCTORS, str(self._NumConductors)
        self._NumPhases = dssInstance.CktElement.NumPhases()

        n = self._NumConductors
        nodes = dssInstance.CktElement.NodeOrder()
        self._Nodes = [nodes[i * n:(i + 1) * n] for i in range((len(nodes) + n - 1) // n)]

        assert len(nodes) == self._NumTerminals * self._NumConductors, \
            f"{self._Nodes} {self._NumTerminals} {self._NumConductors}"

        self._dssInstance = dssInstance

        PropertiesNames = self._dssInstance.Element.AllPropertyNames()
        AS = range(len(PropertiesNames))
        for i, PptName in zip(AS, PropertiesNames):
            self._Parameters[PptName] = str(i)

        CktElmVarDict = dssInstance.CktElement.__dict__
        try:
            for VarName in dssInstance.CktElement.AllVariableNames():
                CktElmVarDict[VarName] = None
        except DSSException as e:
            # Prior to OpenDSSDirect.py v0.8.0 this returned an empty list for non-PC elements.
            # v0.8.0 and later raises an exception. Ignore the error.
            if e.args[1] != "The active circuit element is not a PC Element":
                raise

        for key in CktElmVarDict.keys():
            try:
                self._Variables[key] = getattr(dssInstance.CktElement, key)
            except:
                self._Variables[key] = None
        self.Bus = dssInstance.CktElement.BusNames()
        self.BusCount = len(self.Bus)
        self.sBus = []
        for BusName in self.Bus:
            self._dssInstance.Circuit.SetActiveBus(BusName)
            self.sBus.append(dssBus(self._dssInstance))

    def GetInfo(self):
        return self._Class, self._Name

    def IsValidAttribute(self, VarName):
        # Overridden from base because dssElement has Parameters.
        if VarName in self._Variables:
            return True
        elif VarName in self._Parameters:
            return True
        else:
            return False

    def DataLength(self, VarName):
        if VarName in self._Variables:
            VarValue = self.GetVariable(VarName)
        elif VarName in self._Parameters:
            VarValue = self.GetParameter(VarName)
        else:
            return 0, None

        if  isinstance(VarValue, list):
            return len(VarValue), 'List'
        elif isinstance(VarValue, str):
            return 1, 'String'
        elif isinstance(VarValue, int or float or bool):
            return 1, 'Number'
        else:
            return 0, None

    def GetValue(self, VarName, convert=False):

        if self._dssInstance.Element.Name() != self._FullName:
            self.SetActiveObject()
        fullName = self._dssInstance.Element.Name()
        # logger.debug("123456789123456789123456789123456789123456789123456789")
        # logger.debug(fullName)
        if VarName in self._Variables:
            VarValue = self.GetVariable(VarName, convert=convert)
        elif VarName in self._Parameters:
            VarValue = self.GetParameter(VarName)
            if convert:
                VarValue = ValueByNumber(self._FullName, VarName, VarValue)
        else:
            return None
        return VarValue

    def SetActiveObject(self):
        self._dssInstance.Circuit.SetActiveElement(self._FullName)
        if self._dssInstance.CktElement.Name() != self._dssInstance.Element.Name():
            raise InvalidParameter('Object is not a circuit element')

    def SetParameter(self, Param, Value):
        reply = self._dssInstance.utils.run_command(self._FullName + '.' + Param + ' = ' + str(Value))
        if reply != "":
            raise Exception(f"SetParameter failed: {reply}")
        return self.GetParameter(Param)

    def GetParameter(self, Param):
        if self._dssInstance.Element.Name() != self._FullName:
            self._dssInstance.Circuit.SetActiveElement(self._FullName)
        if self._dssInstance.Element.Name() == self._FullName:
            # This always returns a string.
            # The real value could be a number, a list of numbers, or a string.
            x = self._dssInstance.Properties.Value(Param)
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
    def Conductors(self):
        letters = 'ABCN'
        return [letters[i] for i in range(self._NumConductors)]

    @property
    def ConductorByTerminal(self):
        return [f"{j}{i}" for i in self.Conductors for j in self.Terminals]

    @property
    def NodeOrder(self):
        return self._NodeOrder[:]

    @property
    def NumPhases(self):
        return self._NumPhases

    @property
    def NumConductors(self):
        return self._NumConductors

    @property
    def NumTerminals(self):
        return self._NumTerminals

    @property
    def Terminals(self):
        return list(range(1, self._NumTerminals + 1))
