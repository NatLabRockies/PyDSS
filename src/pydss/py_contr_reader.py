from collections import defaultdict

import os


from pydss.config_data import convert_config_data_to_toml
from pydss.registry import Registry
from pydss.utils.utils import load_data
from pydss.exceptions import InvalidConfiguration, InvalidParameter


class PyContrReader:
    def __init__(self, path):
        self.pyControllers = {}
        filenames = os.listdir(path)
        for filename in filenames:
            py_controller_type, ext = os.path.splitext(filename)
            if filename.startswith("~$"):
                continue
            elif ext == ".xlsx":
                filename = convert_config_data_to_toml(filename)
            elif ext != ".toml":
                continue
            if py_controller_type not in self.pyControllers:
                self.pyControllers[py_controller_type] = {}
            filepath = os.path.join(path, filename)
            assert os.path.exists(filepath), 'path: "{}" does not exist!'.format(filepath)
            for name, controller in load_data(filepath).items():
                if name in self.pyControllers[py_controller_type]:
                    raise InvalidParameter(
                        f"Multiple pydss controller definitions for a single OpenDSS element not allowed: {name}"
                    )
                self.pyControllers[py_controller_type][name] = controller


def read_controller_settings_from_registry(path):
    registry = Registry()
    controllers = defaultdict(dict)
    controller_settings = defaultdict(dict)
    filenames = os.listdir(path)
    for filename in filenames:
        controller_type, ext = os.path.splitext(filename)
        # This file contains a mapping of controller to an array of names.
        # The controller settings must be stored in the pydss registry.

        controller_to_name = load_data(os.path.join(path, filename))

        for controller, names in controller_to_name.items():
            settings = controller_settings[controller_type].get(controller)

            if settings is None:
                if not registry.is_controller_registered(controller_type, controller):
                    raise InvalidConfiguration(
                        f"{controller_type} / {controller} is not registered"
                    )
                settings = registry.read_controller_settings(controller_type, controller)
                controller_settings[controller_type][controller] = settings
            for name in names:
                controllers[controller_type][name] = settings

    return controllers


class PySubscriptionReader:
    def __init__(self, file_path):
        self.SubscriptionList = {}
        if not os.path.exists(file_path):
            raise FileNotFoundError('path: "{}" does not exist!'.format(file_path))

        for elem, elem_data in load_data(file_path).items():
            if elem_data["Subscribe"]:
                self.SubscriptionList[elem] = elem_data


class PyExportReader:
    def __init__(self, file_path):
        self.pyControllers = {}
        self.publicationList = []
        xlsx_filename = os.path.splitext(file_path)[0] + ".xlsx"
        if not os.path.exists(file_path) and os.path.exists(xlsx_filename):
            convert_config_data_to_toml(xlsx_filename)

        if not os.path.exists(file_path):
            raise FileNotFoundError('path: "{}" does not exist!'.format(file_path))

        for elem, elem_data in load_data(file_path).items():
            self.pyControllers[elem] = elem_data["Publish"][:]
            self.pyControllers[elem] += elem_data["NoPublish"]
            for item in elem_data["Publish"]:
                self.publicationList.append(f"{elem} {item}")


globals()["pyContrReader"] = PyContrReader
globals()["pySubscriptionReader"] = PySubscriptionReader
globals()["pyExportReader"] = PyExportReader
