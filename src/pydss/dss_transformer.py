from pydss.dss_element import DssElement
from pydss.value_storage import ValueByNumber
from pydss.value_storage import ValueByList


class DssTransformer(DssElement):
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

    VARIABLE_OUTPUTS_BY_LIST = ["taps"]

    def __init__(self, dss_instance):
        super(DssTransformer, self).__init__(dss_instance)
        self._NumWindings = dss_instance.Transformers.NumWindings()
        self._dssInstance = dss_instance

    @property
    def num_windings(self):
        return self._NumWindings

    @staticmethod
    def chunk_list(values, n_lists):
        return [
            values[i * n_lists : (i + 1) * n_lists]
            for i in range((len(values) + n_lists - 1) // n_lists)
        ]

    def get_value(self, var_name, convert=False):
        if var_name in self._Variables:
            var_value = self.get_variable(var_name, convert=convert)
        elif var_name in self._Parameters:
            var_value = self.get_parameter(var_name)
            if convert:
                if var_name in self.VARIABLE_OUTPUTS_BY_LIST:
                    var_value = var_value[: self.num_windings]
                    var_value = ValueByList(
                        self._FullName,
                        var_name,
                        var_value,
                        ["wdg{}".format(i + 1) for i in range(self.num_windings)],
                    )
                else:
                    var_value = ValueByNumber(self._FullName, var_name, var_value)

        else:
            return None
        return var_value


globals()["dssTransformer"] = DssTransformer

setattr(DssTransformer, "NumWindings", DssTransformer.num_windings)
