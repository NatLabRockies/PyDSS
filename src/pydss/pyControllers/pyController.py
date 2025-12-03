from os.path import dirname, basename, isfile
import glob

from  pydss.pyControllers import Controllers

modules = glob.glob(Controllers.__path__[0]+"/*.py")
pythonFiles = [ basename(f)[:-3] for f in modules if isfile(f) and not f.endswith('__init__.py') ]

from pydss.dssElement import dssElement
ControllerTypes = {}

for file in pythonFiles:
    exec('from pydss.pyControllers.Controllers import {}'.format(file))
    exec('ControllerTypes["{}"] = {}.{}'.format(file, file, file))

def Create(ElmName, ControllerType, Settings, ElmObjectList, dssInstance, dssSolver):

    assert (ControllerType in ControllerTypes), "Definition for '{}' controller not found. \n " \
                                                "Please define the controller in ~pydss\pyControllers\Controllers".format(
        ControllerType
    )
    
    assert (ElmName in ElmObjectList), "'{}' does not exist in the pydss master object dictionary.".format(ElmName)
    relObject = ElmObjectList[ElmName]
    
    # except:
    #     Index = dssInstance.Circuit.SetActiveElement(ElmName)
    #     if int(Index) >= 0:
    #         ElmObjectList[ElmName] = dssElement(dssInstance)
    #         relObject = ElmObjectList[ElmName]
    # else:
    #     return -1

    ObjectController = ControllerTypes[ControllerType](relObject, Settings, dssInstance, ElmObjectList, dssSolver)
    return ObjectController
