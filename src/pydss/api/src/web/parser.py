"""
Takes GET/POST variable dictionary, as might be returned by ``cgi``,
and turns them into lists and dictionaries.
Keys (variable names) can have subkeys, with a ``.`` and
can be numbered with ``-``, like ``a.b-3=something`` means that
the value ``a`` is a dictionary with a key ``b``, and ``b``
is a list, the third(-ish) element with the value ``something``.
Numbers are used to sort, missing numbers are ignored.
This doesn't deal with multiple keys, like in a query string of
``id=10&id=20``, which returns something like ``{'id': ['10',
'20']}``.  That's left to someplace else to interpret.  If you want to
represent lists in this model, you use indexes, and the lists are
explicitly ordered.
If you want to change the character that determines when to split for
a dict or list, both variable_decode and variable_encode take dict_char
and list_char keyword args. For example, to have the GET/POST variables,
``a_1=something`` as a list, you would use a ``list_char='_'``.
"""

import pydss.defaults as defaultSettings
from pydss.utils.utils import load_data
import ast
import os

defaultSettings.__file__
__all__ = ['variable_decode']

master_dict = {
    "Project" : ["Start Year", "Start Day", "Start Time (min)", "End Day", "End Time (min)", "Date offset",
                 "Step resolution (sec)", "Max Control Iterations", "Error tolerance", "Control mode",
                 "Simulation Type", "Project Path", "Active Project", "Active Scenario",
                 "DSS File", "DSS File Absolute Path", "Return Results"],
    "Exports" : ["Export Mode", "Export Style", "Export Format", "Export Compression", "Export Iteration Order",
                 "Export Elements", "Export Data Tables", "Export Data In Memory", "HDF Max Chunk Bytes",
                 "Export Event Log", "Log Results"],
    "Frequency" : ["Enable frequency sweep", "Fundamental frequency", "Start frequency", "End frequency",
                   "frequency increment", "Neglect shunt admittance", "Percentage load in series"],
    "Helics" : ["Co-simulation Mode", "Federate name", "Time delta", "Core type", "Uninterruptible",
                "Helics logging level", "Iterative Mode", 'Max co-iterations', "Error tolerance", 'Broker',
                "Broker port"],
    "Logging" : ["Logging Level", "Log to external file", "Display on screen", "Clear old log file"],
    "MonteCarlo" : ["Number of Monte Carlo scenarios"],
    "Plots" : ["Create dynamic plots", "Open plots in browser"],
}

def bytestream_decode(s):
    lines = s.splitlines()
    filter = b'Content-Disposition: form-data; name='
    result = {}
    for i, l in enumerate(lines):
        if l.startswith(filter):
            l = l.replace(filter, b"").replace(b'"', b'').decode('ascii')
            if '; filename=' in l:
                data = l.replace("; filename=", ":").split(":")
                result[data[0]] = data[1]
            else:
                val = lines[i + 2].decode('ascii')
                result[l] = val
    return result

# TODO: It does not appear that this function is used. Can it be deleted?
# If not, it needs to be updated.
def restructure_dictionary(d):
    global master_dict
    pydss_settings = {}
    path = defaultSettings.__path__._path[0]
    complete_path = os.path.join(path, "simulation.toml")
    defaults = load_data(complete_path)

    for k, i in d.items():
        for key, valid_entries in master_dict.items():
            if k in valid_entries:
                if key not in pydss_settings:
                    pydss_settings[key] = {}
                if i == "False" or i == "false" or i == False:
                    i = False
                elif i == "True" or i == "true" or i == True:
                    i = True
                else:
                    try:
                        i = int(i)
                    except:
                        try:
                            i = float(i)
                        except:
                            pass
                pydss_settings[key][k] = i

    for key, valid_entries in master_dict.items():
        if key in pydss_settings:
            defaults[key].update(pydss_settings[key])

    defaults["Project"]["Scenarios"] =[
        {
            "name": d["Active Scenario"],
            "post_process_infos": []
        }
    ]

    return defaults


def variable_decode(d, dict_char='.', list_char='-'):
    """
    Decode the flat dictionary d into a nested structure.
    """
    result = {}
    for key, value in d.items():
        result[key] = value
    return result
