"""Interface to read pydss files on differing filesystem structures."""

import abc
import io
import json
import os
import sys
import tarfile
import zipfile

import pandas as pd
import toml

from pydss.common import (
    PLOTS_FILENAME,
    PROJECT_TAR,
    PROJECT_ZIP,
    ControllerType,
    ExportMode,
    SIMULATION_SETTINGS_FILENAME,
)
from pydss.exceptions import InvalidConfiguration
from pydss.simulation_input_models import SimulationSettingsModel, load_simulation_settings
from pydss.utils.utils import load_data


STORE_FILENAME = "store.h5"
SCENARIOS = "Scenarios"
PROJECT_DIRECTORIES = ("DSSfiles", "Exports", "Logs", "Scenarios")


class PyDssFileSystemInterface(abc.ABC):
    """Interface to read pydss files on differing filesystem structures."""

    @abc.abstractmethod
    def exists(self, filename):
        """Return True if the filename exists.

        Parameters
        ----------
        filename : str

        Returns
        -------
        bool

        """

    @abc.abstractmethod
    def read_file(self, path):
        """Return the contents of file.

        Parameters
        ----------
        path : str

        Returns
        -------
        str

        """

    @abc.abstractmethod
    def read_csv(self, path):
        """Return a pandas DataFrame from the CSV file.

        Parameters
        ----------
        path : str

        Returns
        -------
        str

        """

    def read_controller_config(self, scenario):
        """Read the controller config for a scenario from disk.

        Parameters
        ----------
        scenario : str
            scenario name

        Returns
        -------
        dict

        """

    @abc.abstractmethod
    def read_export_config(self, scenario):
        """Read the export config for a scenario from disk.

        Parameters
        ----------
        scenario : str
            scenario name

        Returns
        -------
        dict

        """

    @abc.abstractmethod
    def read_plot_config(self, scenario):
        """Read the export config for a scenario from disk.

        Parameters
        ----------
        scenario : str
            scenario name

        Returns
        -------
        dict

        """

    @abc.abstractmethod
    def read_scenario_export_metadata(self, scenario_name):
        """Return the metadata for a scenario's exported data.

        Parameters
        ----------
        scenario_name : str

        Returns
        -------
        dict

        """

    @abc.abstractmethod
    def read_scenario_pv_profiles(self, scenario_name):
        """Return the PV profiles for a scenario.

        Parameters
        ----------
        scenario_name : str

        Returns
        -------
        dict

        """

    @property
    def scenario_names(self):
        """Return the scenario names in the project.

        Returns
        -------
        list

        """
        return [x.name for x in self._settings.project.scenarios]

    @property
    @abc.abstractmethod
    def simulation_config(self):
        """Return the config from the simulation settings file.

        Returns
        -------
        dict

        """

    def _check_scenarios(self):
        scenarios = self._list_scenario_names()

        if scenarios is None:
            return

        exp_scenarios = self.scenario_names
        exp_scenarios.sort()

        for scenario in exp_scenarios:
            if scenario not in scenarios:
                raise InvalidConfiguration(
                    f"{scenario} is not a valid scenario. Valid scenarios: {scenarios}"
                )

    @abc.abstractmethod
    def _list_scenario_names(self):
        """Return the scenario names on disk.

        Returns
        -------
        list

        """


class PyDssFileSystemInterface(PyDssFileSystemInterface):
    """Reads pydss files when the project is expanded into directories."""

    def __init__(self, project_dir, simulation_file):
        self._project_dir = project_dir
        self._scenarios_dir = os.path.join(self._project_dir, SCENARIOS)
        self._dss_dir = os.path.join(self._project_dir, "DSSfiles")

        self._settings = load_simulation_settings(os.path.join(self._project_dir, simulation_file))

        self._check_scenarios()

    def _get_full_path(self, path):
        return os.path.join(self._project_dir, path)

    def exists(self, filename):
        return os.path.exists(filename)

    def read_file(self, path):
        with open(self._get_full_path(path)) as f_in:
            return f_in.read()

    def read_csv(self, path):
        return pd.read_csv(self._get_full_path(path))

    def _list_scenario_names(self):
        scenarios = [
            x
            for x in os.listdir(self._scenarios_dir)
            if os.path.isdir(os.path.join(self._scenarios_dir, x))
        ]
        scenarios.sort()
        return scenarios

    def read_controller_config(self, scenario):
        controllers = {}
        path = os.path.join(self._project_dir, SCENARIOS, scenario, "pyControllerList")
        if not os.path.exists(path):
            return controllers
        for filename in os.listdir(path):
            base, ext = os.path.splitext(filename)
            if ext == ".toml":
                controller_type = ControllerType(base)
                controllers[controller_type] = load_data(os.path.join(path, filename))

        return controllers

    def read_export_config(self, scenario):
        exports = {}
        path = os.path.join(self._project_dir, SCENARIOS, scenario, "ExportLists")
        for filename in os.listdir(path):
            base, ext = os.path.splitext(filename)
            if ext == ".toml":
                export_mode = ExportMode(base)
                exports[export_mode] = load_data(os.path.join(path, filename))

        return exports

    def read_plot_config(self, scenario):
        path = os.path.join(self._project_dir, SCENARIOS, scenario, "pyPlotList", PLOTS_FILENAME)
        return load_data(path)

    def read_scenario_export_metadata(self, scenario_name):
        filename = os.path.join(
            self._project_dir,
            "Exports",
            scenario_name,
            "metadata.json",
        )
        if not self.exists(filename):
            return {}
        return load_data(filename)

    def read_scenario_pv_profiles(self, scenario_name):
        filename = os.path.join(
            self._project_dir,
            "Exports",
            scenario_name,
            "pv_profiles.json",
        )
        if not os.path.exists(filename):
            return {}
        return load_data(filename)

    @property
    def simulation_config(self):
        return self._settings


class PyDssArchiveFileInterfaceBase(PyDssFileSystemInterface):
    """Base class for archive types."""

    def __init__(self, project_dir):
        self._project_dir = project_dir
        data = self._load_data(SIMULATION_SETTINGS_FILENAME)
        self._settings = SimulationSettingsModel(**data)
        self._check_scenarios()

    def _load_data(self, path):
        ext = os.path.splitext(path)[1]
        if ext == ".json":
            return self._read_json(path)
        if ext == ".toml":
            return self._read_toml(path)

        raise Exception(f"unsupported extension {ext}")

    def _read_json(self, path):
        return json.loads(self.read_file(path))

    def _read_toml(self, path):
        return toml.loads(self.read_file(path))

    def _list_scenario_names(self):
        store_filename = os.path.join(self._project_dir, STORE_FILENAME)
        if not os.path.exists(store_filename):
            return None

        scenarios = None
        with pd.HDFStore(store_filename, "r") as store:
            for path, subgroups, _ in store.walk():
                if path == "/Exports":
                    scenarios = subgroups
                    break

        # scenarios will be None if no exports were defined.
        if scenarios:
            scenarios.sort()
        return scenarios

    @staticmethod
    def normalize_path(path):
        return os.path.normpath(path).replace("\\", "/")

    @property
    def simulation_config(self):
        return self._settings

    def read_controller_config(self, scenario):
        # Not currently needed for reading projects.
        pass

    def read_csv(self, path):
        assert False, "Not implemented"

    def read_file(self, path):
        assert False, "Not implemented"

    def read_export_config(self, scenario):
        # Not currently needed for reading projects.
        pass

    def read_plot_config(self, scenario):
        # Not currently needed for reading projects.
        pass

    def read_scenario_export_metadata(self, scenario_name):
        filename = os.path.join(
            "Exports",
            scenario_name,
            "metadata.json",
        )
        if not self.exists(self.normalize_path(filename)):
            return {}
        return self._load_data(filename)

    def read_scenario_pv_profiles(self, scenario_name):
        filename = os.path.join(
            "Exports",
            scenario_name,
            "pv_profiles.json",
        )
        try:
            return self._load_data(filename)
        except KeyError:
            # The file isn't stored in the archive.
            return {}


class PyDssTarFileInterface(PyDssArchiveFileInterfaceBase):
    """Reads pydss files when the project is archived in tar file."""

    def __init__(self, project_dir):
        tar_path = os.path.join(project_dir, PROJECT_TAR)
        self._tar = tarfile.open(tar_path)
        super(PyDssTarFileInterface, self).__init__(project_dir)

    def __del__(self):
        if not self._tar.closed:
            self._tar.close()

    def exists(self, filename):
        return filename in self._tar.getnames()

    def read_file(self, path):
        if sys.platform == "win32":
            path = self.normalize_path(path)
        return self._tar.extractfile(path).read().decode("utf-8")

    def read_csv(self, path):
        return pd.read_csv(self._tar.extractfile(os.path.normpath(path).replace("\\", "/")))


class PyDssZipFileInterface(PyDssArchiveFileInterfaceBase):
    """Reads pydss files when the project is archived in zip file."""

    def __init__(self, project_dir):
        self._zip = zipfile.ZipFile(os.path.join(project_dir, PROJECT_ZIP))
        super(PyDssZipFileInterface, self).__init__(project_dir)

    def __del__(self):
        self._zip.close()

    def exists(self, filename):
        return filename in self._zip.namelist()

    def read_file(self, path):
        if sys.platform == "win32":
            path = self.normalize_path(path)
        data = self._zip.read(path)
        ext = os.path.splitext(path)[1]
        if ext != ".h5":
            data = data.decode("utf-8")
        return data

    def read_csv(self, path):
        if sys.platform == "win32":
            path = self.normalize_path(path)
        return pd.read_csv(io.BytesIO(self._zip.read(path)))
