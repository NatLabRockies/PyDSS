from os.path import basename, isfile
from pydss.profile_manager import hooks
import importlib
import glob


modules = glob.glob(hooks.__path__[0] + "/*.py")
python_files = [
    (basename(f)[:-3], f) for f in modules if isfile(f) and not f.endswith("__init__.py")
]

profile_interfaces = {}
modules_instances = {}
for module, file in python_files:
    spec = importlib.util.spec_from_file_location(module, file)
    modules_instances[module] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modules_instances[module])
    profile_interfaces[module] = modules_instances[module].ProfileManager


def create(sim_instance, solver, settings, logger, **kwargs):
    source_type = settings.profiles.source_type.value
    if source_type in profile_interfaces:
        post_processor = profile_interfaces[source_type](
            sim_instance, solver, settings, logger, **kwargs
        )
    else:
        raise ModuleNotFoundError(
            f"{source_type} is not a valid source type. Valid values are {','.join(list(profile_interfaces.keys()))}"
        )
    return post_processor


ProfileInterfaces = profile_interfaces
Create = create
