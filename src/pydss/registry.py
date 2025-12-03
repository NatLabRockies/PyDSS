"""Manages pydss customized modules."""

from collections import defaultdict
from pathlib import Path
import copy
import sys
import os

from loguru import logger

import pydss
from pydss.common import ControllerType, CONTROLLER_TYPES
from pydss.exceptions import InvalidConfiguration, InvalidParameter
from pydss.utils.utils import dump_data, load_data


DEFAULT_REGISTRY = {
    "Controllers": {
        ControllerType.PV_CONTROLLER.value: [
            {
                "name": "NO_VRT",
                "filename": os.path.join(
                    os.path.dirname(getattr(pydss, "__path__")[0]),
                    "pydss/pyControllers/Controllers/Settings/PvControllers.toml",
                ),
            },
            {
                "name": "cpf",
                "filename": os.path.join(
                    os.path.dirname(getattr(pydss, "__path__")[0]),
                    "pydss/pyControllers/Controllers/Settings/PvControllers.toml",
                ),
            },
            {
                "name": "volt-var",
                "filename": os.path.join(
                    os.path.dirname(getattr(pydss, "__path__")[0]),
                    "pydss/pyControllers/Controllers/Settings/PvControllers.toml",
                ),
            },
        ],
        ControllerType.PV_VOLTAGE_RIDETHROUGH.value: [],
        ControllerType.SOCKET_CONTROLLER.value: [],
        ControllerType.STORAGE_CONTROLLER.value: [],
        ControllerType.XMFR_CONTROLLER.value: [],
        ControllerType.MOTOR_STALL.value: [],
        ControllerType.MOTOR_STALL_SIMPLE.value: [],
        ControllerType.FAULT_CONTROLLER.value: [],
    },
}

REQUIRED_CONTROLLER_FIELDS = ("name", "filename")


class Registry:
    """Manages controllers registered with pydss."""

    _REGISTRY_FILENAME = ".pydss-registry.json"

    def __init__(self, registry_filename=None):
        if registry_filename is None:
            self._registry_filename = Path.home() / self._REGISTRY_FILENAME
        else:
            self._registry_filename = Path(registry_filename)

        self._controllers = {x: {} for x in CONTROLLER_TYPES}
        data = copy.deepcopy(DEFAULT_REGISTRY)
        for controller_type, controllers in DEFAULT_REGISTRY["Controllers"].items():
            for controller in controllers:
                path = Path(controller["filename"])
                if not path.exists():
                    raise InvalidConfiguration(f"Default controller file={path} does not exist")

        # This is written to work with legacy versions where default controllers were
        # written to the registry.
        if self._registry_filename.exists():
            registered = load_data(self._registry_filename)
            to_delete = []
            for controller_type, controllers in registered["Controllers"].items():
                for i, controller in enumerate(controllers):
                    path = Path(controller["filename"])
                    if not path.exists():
                        name = controller["name"]
                        msg = (
                            f"The registry contains a controller with an invalid file. "
                            f"Type={controller_type} name={name} file={path}.\nWould you like to "
                            "delete it? (y/n) -> "
                        )
                        response = input(msg).lower()
                        if response == "y":
                            to_delete.append((controller_type, i))
                            continue
                        else:
                            logger.error(
                                "Exiting because the registry %s is invalid",
                                self._registry_filename,
                            )
                            sys.exit(1)
                    if not self._is_default_controller(controller_type, controller["name"]):
                        data["Controllers"][controller_type].append(controller)
            if to_delete:
                for ref in reversed(to_delete):
                    registered["Controllers"][ref[0]].pop(ref[1])
                backup = str(self._registry_filename) + ".bk"
                self._registry_filename.rename(backup)
                dump_data(registered, self._registry_filename, indent=2)
                logger.info("Fixed the registry and moved the original to %s", backup)

        for controller_type, controllers in data["Controllers"].items():
            for controller in controllers:
                self._add_controller(controller_type, controller)

    def _add_controller(self, controller_type, controller):
        name = controller["name"]
        filename = controller["filename"]
        if self.is_controller_registered(controller_type, name):
            raise InvalidParameter(f"{controller_type} / {name} is already registered")
        if not os.path.exists(filename):
            raise InvalidParameter(f"{filename} does not exist.")
        # Make sure the file can be parsed.
        load_data(filename)

        self._controllers[controller_type][name] = controller

    @staticmethod
    def _is_default_controller(controller_type, name):
        for controller in DEFAULT_REGISTRY["Controllers"][controller_type]:
            if controller["name"] == name:
                return True
        return False

    def _serialize_registry(self):
        data = {"Controllers": defaultdict(list)}
        has_entries = False
        for controller_type in self._controllers:
            for controller in self._controllers[controller_type].values():
                # Serializing default controllers is not necessary and causes problems
                # when the software is upgraded or installed to a new location.
                if not self._is_default_controller(controller_type, controller["name"]):
                    data["Controllers"][controller_type].append(controller)
                    has_entries = True

        if has_entries:
            filename = self.registry_filename
            dump_data(data, filename, indent=2)
            logger.debug("Serialized data to %s", filename)

    def is_controller_registered(self, controller_type, name):
        """Check if the controller is registered"""
        return name in self._controllers[controller_type]

    def list_controllers(self, controller_type):
        """Return a list of registered controllers.

        Returns
        -------
        list of dict

        """
        return list(self._controllers[controller_type].values())

    def read_controller_settings(self, controller_type, name):
        """Return the settings for the controller.

        Parameters
        ----------
        name : str

        Raises
        ------
        InvalidParameter
            Raised if name is not registered.

        """
        controller = self._controllers[controller_type].get(name)
        if controller is None:
            raise InvalidParameter(f"{controller_type} / {name} is not registered")
        return load_data(controller["filename"])[name]

    def register_controller(self, controller_type, controller):
        """Registers a controller in the registry.

        Parameters
        ----------
        controller_type : str
        controller : dict

        Raises
        ------
        InvalidParameter
            Raised if the controller is invalid.

        """

        self._add_controller(controller_type, controller)
        self._serialize_registry()
        logger.debug("Registered controller %s / %s", controller_type, controller["name"])

    @property
    def registry_filename(self):
        """Return the filename that stores the registry."""
        return self._registry_filename

    def reset_defaults(self, controllers_only=False):
        """Reset the registry to its default values."""
        if self._registry_filename.exists():
            self._registry_filename.unlink()
        for controllers in self._controllers.values():
            controllers.clear()
        for controller_type, controllers in DEFAULT_REGISTRY["Controllers"].items():
            for controller in controllers:
                self._add_controller(controller_type, controller)

        logger.debug("Initialized registry to its defaults.")

    def show_controllers(self):
        """Show the registered controllers."""
        print("Pydss Controllers:")
        for controller_type in self._controllers:
            print(f"Controller Type:  {controller_type}")
            controllers = list(self._controllers[controller_type].values())
            if controllers:
                for controller in controllers:
                    name = controller["name"]
                    filename = controller["filename"]
                    print(f"  {name}:  {filename}")
            else:
                print("  None")

    def unregister_controller(self, controller_type, name):
        """Unregisters a controller.

        Parameters
        ----------
        controller_type : str
        name : str

        """
        if not self.is_controller_registered(controller_type, name):
            raise InvalidParameter(f"{controller_type} / {name} isn't registered")
        if self._is_default_controller(controller_type, name):
            raise InvalidParameter(f"Cannot unregister a default controller")

        self._controllers[controller_type].pop(name)
        self._serialize_registry()
