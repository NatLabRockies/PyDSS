"""Contains functionality to configure pydss simulations."""
import os
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

import h5py

from loguru import logger

import pydss
from pydss.common import PROJECT_TAR, PROJECT_ZIP, CONTROLLER_TYPES, \
    SIMULATION_SETTINGS_FILENAME, DEFAULT_SIMULATION_SETTINGS_FILE, \
    ControllerType, ExportMode, SnapshotTimePointSelectionMode, MONTE_CARLO_SETTINGS_FILENAME,\
    filename_from_enum, DEFAULT_MONTE_CARLO_SETTINGS_FILE,\
    SUBSCRIPTIONS_FILENAME, DEFAULT_SUBSCRIPTIONS_FILE, OPENDSS_MASTER_FILENAME, \
    RUN_SIMULATION_FILENAME
from pydss.exceptions import InvalidParameter, InvalidConfiguration
from pydss.pyDSS import instance
from pydss.pydss_fs_interface import PyDssFileSystemInterface, \
    PyDssArchiveFileInterfaceBase, PyDssTarFileInterface, \
    PyDssZipFileInterface, PROJECT_DIRECTORIES, \
    SCENARIOS, STORE_FILENAME
from pydss.reports.reports import REPORTS_DIR
from pydss.registry import Registry
from pydss.simulation_input_models import (
    ScenarioModel,
    ScenarioPostProcessModel,
    SimulationSettingsModel,
    SnapshotTimePointSelectionConfigModel,
    create_simulation_settings,
    load_simulation_settings,
    dump_settings,
)
from pydss.utils.dss_utils import read_pv_systems_from_dss_file
from pydss.utils.utils import dump_data, load_data

from shutil import copytree


DATA_FORMAT_VERSION = "1.0.2"

READ_CONTROLLER_FUNCTIONS = {
    ControllerType.PV_CONTROLLER.value: read_pv_systems_from_dss_file,
}


class PyDssProject:
    """Represents the project options for a pydss simulation."""

    _SKIP_ARCHIVE = (PROJECT_ZIP, PROJECT_TAR, STORE_FILENAME, REPORTS_DIR)

    def __init__(self, path, name, scenarios, settings: SimulationSettingsModel, fs_intf=None,
                 simulation_file=SIMULATION_SETTINGS_FILENAME):
        self._name = name
        self._scenarios = scenarios
        self._settings = settings
        self._project_dir = os.path.join(path, self._name)
        if simulation_file is None:
            self._simulation_file = os.path.join(self._project_dir, SIMULATION_SETTINGS_FILENAME)
        else:
            self._simulation_file = simulation_file
        self._scenarios_dir = os.path.join(self._project_dir, SCENARIOS)
        self._fs_intf = fs_intf  # Only needed for reading a project that was
                                 # already executed.
        self._hdf_store = None
        self._estimated_space = {}

    @property
    def dss_files_path(self):
        """Return the path containing OpenDSS files.

        Returns
        -------
        str

        """
        return os.path.join(self._project_dir, "DSSfiles")

    def export_path(self, scenario):
        """Return the path containing export data.

        Parameters
        ----------
        scenario : str

        Returns
        -------
        str

        """
        return os.path.join(self._project_dir, "Exports", scenario)

    @property
    def hdf_store(self):
        """Return the HDFStore

        Returns
        -------
        pd.HDFStore

        """
        if self._hdf_store is None:
            raise InvalidConfiguration("hdf_store is not defined")
        return self._hdf_store

    @property
    def fs_interface(self):
        """Return the interface object used to read files.

        Returns
        -------
        PyDssFileSystemInterface

        """
        if self._fs_intf is None:
            raise InvalidConfiguration("fs interface is not defined")
        return self._fs_intf

    def get_hdf_store_filename(self):
        """Return the HDFStore filename.

        Returns
        -------
        str
            Path to the HDFStore.

        Raises
        ------
        InvalidConfiguration
            Raised if no store exists.

        """
        filename = os.path.join(self._project_dir, STORE_FILENAME)
        if not os.path.exists(filename):
            raise InvalidConfiguration(f"HDFStore does not exist: {filename}")

        return filename

    def get_post_process_directory(self, scenario_name):
        """Return the post-process output directory for scenario_name.

        Parameters
        ----------
        scenario_name : str

        Returns
        -------
        str

        """
        # Make sure the scenario exists. This will throw if not.
        self.get_scenario(scenario_name)
        return os.path.join(
            self._project_dir, "Scenarios", scenario_name, "PostProcess"
        )

    def get_scenario(self, name):
        """Return the scenario with name.

        Parameters
        ----------
        name : str

        Returns
        -------
        PyDssScenario

        """
        for scenario in self._scenarios:
            if scenario.name == name:
                return scenario

        raise InvalidParameter(f"{name} is not a valid scenario")

    @property
    def name(self):
        """Return the project name.

        Returns
        -------
        str

        """
        return self._name

    @property
    def project_path(self):
        """Return the path to the project.

        Returns
        -------
        str

        """
        return self._project_dir

    @property
    def scenarios(self):
        """Return the project scenarios.

        Returns
        -------
        list
            list of PyDssScenario

        """
        return self._scenarios

    @property
    def simulation_config(self):
        """Return the simulation configuration

        Returns
        -------
        dict

        """
        return self._settings

    @property
    def estimated_space(self):
        """Return the estimated space in bytes.
        
        Returns
        -------
        int
        """
        return self._estimated_space

    def serialize(self, opendss_project_folder):
        """Create the project on the filesystem."""
        os.makedirs(self._project_dir, exist_ok=True)
        for name in PROJECT_DIRECTORIES:
            os.makedirs(os.path.join(self._project_dir, name), exist_ok=True)
        if opendss_project_folder:
            dest = os.path.join(self._project_dir, PROJECT_DIRECTORIES[0])
            copytree(opendss_project_folder, dest)
        self._serialize_scenarios()
        dump_settings(
            self._settings,
            os.path.join(self._project_dir, self._simulation_file),
        )
        logger.info("Initialized directories in %s", self._project_dir)

    @classmethod

    def create_project(cls, path, name, scenarios, simulation_config=None, options=None,
                       simulation_file=SIMULATION_SETTINGS_FILENAME, opendss_project_folder=None,
                       master_dss_file=OPENDSS_MASTER_FILENAME, force=False):
        """Create a new PyDssProject on the filesystem.

        Parameters
        ----------
        path : str
            path in which to create directories
        name : str
            project name
        scenarios : list
            list of PyDssScenario objects
        simulation_config : str
            simulation config file; if None, use default

        """
        if simulation_config is None:
            scenario_names = [x.name for x in scenarios]
            simulation_config = create_simulation_settings(path, name, scenario_names, force=force)
        simulation_config = load_data(simulation_config)
        if options is not None:
            for category, category_options in options.items():
                simulation_config[category].update(category_options)
        if master_dss_file:
            simulation_config["project"]["dss_file"] = master_dss_file
        simulation_config["project"]["project_path"] = path
        simulation_config["project"]["active_project"] = name
        settings = SimulationSettingsModel(**simulation_config)
        project = cls(
            path=path,
            name=name,
            scenarios=scenarios,
            settings=settings,
            simulation_file=simulation_file,
        )
        project.serialize(opendss_project_folder=opendss_project_folder)
        sc_names = project.list_scenario_names()
        logger.info("Created project=%s with scenarios=%s at %s", name,
                    sc_names, path)
        return project

    def read_scenario_export_metadata(self, scenario_name):
        """Return the metadata for a scenario's exported data.

        Parameters
        ----------
        scenario_name : str

        Returns
        -------
        dict

        """
        if self._fs_intf is None:
            raise InvalidConfiguration("pydss fs interface is not defined")

        if scenario_name not in self.list_scenario_names():
            raise InvalidParameter(f"invalid scenario: {scenario_name}")

        return self._fs_intf.read_scenario_export_metadata(scenario_name)

    def list_scenario_names(self):
        return [x.name for x in self.scenarios]

    def run(self, logging_configured=True, tar_project=False, zip_project=False, dry_run=False):
        """Run all scenarios in the project."""
        if isinstance(self._fs_intf, PyDssArchiveFileInterfaceBase):
            raise InvalidConfiguration("cannot run from an archived project")
        if tar_project and zip_project:
            raise InvalidParameter("tar_project and zip_project cannot both be True")
        if self._settings.project.dss_file == "":
            raise InvalidConfiguration("a valid opendss file needs to be passed")

        inst = instance()
        if not logging_configured:
            if self._settings.logging.enable_console:
                console_level = "INFO"
            else:
                console_level = "ERROR"
            if self._settings.logging.enable_file:
                filename = os.path.join(self._project_dir, "Logs", "pydss.log")
            else:
                filename = None
            file_level = "INFO"
            logger.level(console_level)
            if filename:
                logger.add(filename)
            
        if dry_run:
            store_filename = os.path.join(tempfile.gettempdir(), STORE_FILENAME)
        else:
            store_filename = os.path.join(self._project_dir, STORE_FILENAME)
            self._dump_simulation_settings()

        driver = None
        if self._settings.exports.export_data_in_memory:
            driver = "core"
        if os.path.exists(store_filename):
            os.remove(store_filename)

        try:
            # This ensures that all datasets are flushed and closed after each
            # scenario. If there is an unexpected crash in a later scenario then
            # the file will still be valid for completed scenarios.
            for scenario in self._scenarios:
                with h5py.File(store_filename, mode="a", driver=driver) as hdf_store:
                    self._hdf_store = hdf_store
                    self._hdf_store.attrs["version"] = DATA_FORMAT_VERSION
                    self._settings.project.active_scenario = scenario.name
                    inst.run(self._settings, self, scenario, dry_run=dry_run)
                    self._estimated_space[scenario.name] = inst.get_estimated_space()

            export_tables = self._settings.exports.export_data_tables
            generate_reports = bool(self._settings.reports)
            if not dry_run and (export_tables or generate_reports):
                # Hack. Have to import here. Need to re-organize to fix.
                from pydss.pydss_results import PyDssResults
                results = PyDssResults(self._project_dir)
                if export_tables:
                    for scenario in results.scenarios:
                        scenario.export_data()

                if generate_reports:
                    results.generate_reports()

        except Exception:
            logger.exception("Simulation failed")
            raise

        finally:
            logger.remove()
            if tar_project:
                self._tar_project_files()
            elif zip_project:
                self._zip_project_files()

            if dry_run and os.path.exists(store_filename):
                os.remove(store_filename)

    def _dump_simulation_settings(self):
        # Various settings may have been updated. Write the actual settings to a file.
        filename = os.path.join( self._project_dir, RUN_SIMULATION_FILENAME)
        dump_settings(self._settings, filename)

    def _serialize_scenarios(self):
        scenarios = []
        for scenario in self._scenarios:
            cfg = scenario.snapshot_time_point_selection_config or SnapshotTimePointSelectionConfigModel()
            model = ScenarioModel(
                name=scenario.name,
                post_process_infos=[],
                snapshot_time_point_selection_config=cfg,
            )
            model.post_process_infos = scenario.post_process_infos
            scenarios.append(model)
            scenario.serialize(
                os.path.join(self._scenarios_dir, scenario.name)
            )

        self._settings.project.scenarios = scenarios

    def _tar_project_files(self, delete=True):
        orig = os.getcwd()
        os.chdir(self._project_dir)
        skip_names = (PROJECT_ZIP, STORE_FILENAME, REPORTS_DIR)
        try:
            filename = PROJECT_TAR
            to_delete = []
            with tarfile.open(filename, "w") as tar:
                for name in os.listdir("."):
                    if name in self._SKIP_ARCHIVE:
                        continue
                    tar.add(name)
                    if delete:
                        to_delete.append(name)

            for name in to_delete:
                if os.path.isfile(name):
                    os.remove(name)
                else:
                    shutil.rmtree(name)

            path = os.path.join(self._project_dir, filename)
        finally:
            os.chdir(orig)

    def _zip_project_files(self, delete=True):
        orig = os.getcwd()
        os.chdir(self._project_dir)
        try:
            filename = PROJECT_ZIP
            to_delete = []
            with zipfile.ZipFile(filename, "w") as zipf:
                for root, dirs, files in os.walk("."):
                    if delete and root == ".":
                        to_delete += dirs
                    for filename in files:
                        if root == "." and filename in self._SKIP_ARCHIVE:
                            continue
                        path = os.path.join(root, filename)
                        zipf.write(path)
                        # We delete files and directories at the root only.
                        if delete and root == ".":
                            to_delete.append(path)

            for name in to_delete:
                if os.path.isfile(name):
                    os.remove(name)
                else:
                    shutil.rmtree(name)

            path = os.path.join(self._project_dir, filename)
        finally:
            os.chdir(orig)

    @staticmethod
    def load_simulation_settings(project_path, simulations_file):
        """Return the simulation settings for a project, using defaults if the
        file is not defined.

        Parameters
        ----------
        project_path : Path

        Returns
        -------
        SimulationSettingsModel

        """
        filename = project_path / simulations_file
        if not filename.exists():
            filename = project_path / DEFAULT_SIMULATION_SETTINGS_FILE
            assert filename.exists()
        return load_simulation_settings(filename)

    @classmethod
    def load_project(
        cls,
        path,
        options=None,
        in_memory=False,
        simulation_file=SIMULATION_SETTINGS_FILENAME,
    ):
        """Load a PyDssProject from directory.

        Parameters
        ----------
        path : str
            full path to existing project
        options : dict
            options that override the config file
        in_memory : bool
            If True, load all exported data into memory.

        """
        name = os.path.basename(path)
        #if simulation_file is None:
            #simulation_file = SIMULATION_SETTINGS_FILENAME

        if os.path.exists(os.path.join(path, PROJECT_TAR)):
            fs_intf = PyDssTarFileInterface(path)
        elif os.path.exists(os.path.join(path, PROJECT_ZIP)):
            fs_intf = PyDssZipFileInterface(path)
        else:
            fs_intf = PyDssFileSystemInterface(path, simulation_file)

        simulation_config = fs_intf.simulation_config.dict(by_alias=False)
        if options is not None:
            for category, params in options.items():
                if category not in simulation_config:
                    simulation_config[category] = {}
                simulation_config[category].update(params)
            logger.info("Overrode config options: %s", options)

        settings = SimulationSettingsModel(**simulation_config)
        scenarios = [
            PyDssScenario.deserialize(
                fs_intf,
                x.name,
                post_process_infos=x.post_process_infos,
            )
            for x in settings.project.scenarios
        ]

        return PyDssProject(
            os.path.dirname(path),
            name,
            scenarios,
            settings,
            fs_intf=fs_intf,
        )

    @classmethod
    def run_project(cls, path, options=None, tar_project=False, zip_project=False, simulation_file=None, dry_run=False):

        """Load a PyDssProject from directory and run all scenarios.

        Parameters
        ----------
        path : str
            full path to existing project
        options : dict
            options that override the config file
        tar_project : bool
            tar project files after successful execution
        zip_project : bool
            zip project files after successful execution
        dry_run: bool
            dry run for getting estimated space.
        """

        project = cls.load_project(path, options=options, simulation_file=simulation_file)
        return project.run(tar_project=tar_project, zip_project=zip_project, dry_run=dry_run)

    def read_scenario_settings(self, scenario):
        """Read the simulation settings file for the scenario.

        Parameters
        ----------
        scenario : str
            Scenario name

        Returns
        -------
        SimulationSettingsModel

        """
        scenario_path = Path(self._project_dir) / "Scenarios" / scenario
        if not scenario_path.exists():
            raise InvalidParameter(f"scenario={scenario} is not present")

        settings_file = scenario_path / RUN_SIMULATION_FILENAME
        if not settings_file.exists():
            raise InvalidConfiguration(f"{RUN_SIMULATION_FILENAME} does not exist. Was the scenario run?")

        return load_simulation_settings(settings_file)

    def read_scenario_time_settings(self, scenario):
        """Return the simulation time-related settings for the scenario.

        Parameters
        ----------
        scenario : str
            Scenario name

        Returns
        -------
        dict

        """
        settings = self.read_scenario_settings(scenario).project
        data = {}
        for key in (
            "start_time",
            "simulation_duration_min",
            "loadshape_start_time",
            "step_resolution_sec",
        ):
            data[key] = getattr(settings, key)
        return data


class PyDssScenario:
    """Represents a pydss Scenario."""

    DEFAULT_CONTROLLER_TYPES = (ControllerType.PV_CONTROLLER,)
    DEFAULT_EXPORT_MODE = ExportMode.EXPORTS
    _SCENARIO_DIRECTORIES = (
        "ExportLists",
        "pyControllerList",
        "pyPlotList",
        "PostProcess",
        'Monte_Carlo'
    )
    REQUIRED_POST_PROCESS_FIELDS = ("script", "config_file")

    def __init__(self, name, controller_types=None, controllers=None,
                 export_modes=None, exports=None,
                 post_process_infos=None, 
                 snapshot_time_point_selection_config=None):
        self.name = name
        self.post_process_infos = []
        self.snapshot_time_point_selection_config = None

        if (controller_types is None and controllers is None):
            self.controllers = {}
        elif controller_types is not None:
            self.controllers = {
                x: self.load_controller_config_from_type(x)
                for x in controller_types
            }
        elif isinstance(controllers, str):
            basename = os.path.splitext(os.path.basename(controllers))[0]
            controller_type = ControllerType(basename)
            self.controllers = {controller_type: load_data(controllers)}
        else:
            assert isinstance(controllers, dict)
            self.controllers = controllers

        if export_modes is not None and exports is not None:
            raise InvalidParameter(
                "export_modes and exports cannot both be set"
            )
        if (export_modes is None and exports is None):
            mode = PyDssScenario.DEFAULT_EXPORT_MODE
            self.exports = {mode: self.load_export_config_from_mode(mode)}
        elif export_modes is not None:
            self.exports = {
                x: self.load_export_config_from_mode(x) for x in export_modes
            }
        elif isinstance(exports, str):
            mode = ExportMode(os.path.splitext(os.path.basename(exports))[0])
            self.exports = {mode: load_data(exports)}
        else:
            assert isinstance(exports, dict)
            self.exports = exports
        print(self.exports)
        if post_process_infos is not None:
            for pp_info in post_process_infos:
                if isinstance(pp_info, dict):
                    pp_info = ScenarioPostProcessModel(**pp_info)
                self.add_post_process(pp_info)

        if snapshot_time_point_selection_config is not None:
            # Ensure the mode is valid.
            SnapshotTimePointSelectionMode(snapshot_time_point_selection_config["mode"])
            self.snapshot_time_point_selection_config = snapshot_time_point_selection_config

    @classmethod
    def deserialize(cls, fs_intf, name, post_process_infos):
        """Deserialize a PyDssScenario from a path.

        Parameters
        ----------
        fs_intf : PyDssFileSystemInterface
            object to read on-disk information
        name : str
            scenario name
        post_process_infos : list
            list of post_process_info dictionaries

        Returns
        -------
        PyDssScenario

        """
        controllers = fs_intf.read_controller_config(name)
        exports = fs_intf.read_export_config(name)

        return cls(
            name,
            controllers=controllers,
            exports=exports,
            post_process_infos=post_process_infos,
        )

    def serialize(self, path):
        """Serialize a PyDssScenario to a directory.

        Parameters
        ----------
        path : str
            full path to scenario

        """
        os.makedirs(path, exist_ok=True)
        for name in self._SCENARIO_DIRECTORIES:
            os.makedirs(os.path.join(path, name), exist_ok=True)

        for controller_type, controllers in self.controllers.items():
            filename = os.path.join(
                path, "pyControllerList", filename_from_enum(controller_type)
            )
            dump_data(controllers, filename)

        for mode, exports in self.exports.items():
            dump_data(
                exports,
                os.path.join(path, "ExportLists", filename_from_enum(mode))
            )

        dump_data(
            load_data(DEFAULT_MONTE_CARLO_SETTINGS_FILE),
            os.path.join(path, "Monte_Carlo", MONTE_CARLO_SETTINGS_FILENAME)
        )

        dump_data(
            load_data(DEFAULT_SUBSCRIPTIONS_FILE),
            os.path.join(path, "ExportLists", SUBSCRIPTIONS_FILENAME)
        )

    @staticmethod
    def load_controller_config_from_type(controller_type):
        """Load a default controller config from a type.

        Parameters
        ----------
        controller_type : ControllerType

        Returns
        -------
        dict

        """

        path = os.path.join(
            os.path.dirname(getattr(pydss, "__path__")[0]),
            "pydss",
            "defaults",
            "pyControllerList",
            filename_from_enum(controller_type),
        )

        return load_data(path)

    @staticmethod
    def load_export_config_from_mode(export_mode):
        """Load a default export config from a type.

        Parameters
        ----------
        export_mode : ExportMode

        Returns
        -------
        dict

        """
        path = os.path.join(
            os.path.dirname(getattr(pydss, "__path__")[0]),
            "pydss",
            "defaults",
            "ExportLists",
            filename_from_enum(export_mode),
        )

        return load_data(path)

    def add_post_process(self, post_process_info):
        """Add a post-process script to a scenario.

        Parameters
        ----------
        post_process_info : dict
            Must define all fields in PyDssScenario.REQUIRED_POST_PROCESS_FIELDS

        """
        config_file = post_process_info.config_file
        if config_file and not os.path.exists(config_file):
            raise InvalidParameter(f"{config_file} does not exist")

        self.post_process_infos.append(post_process_info)


def load_config(path):
    """Return a configuration from files.

    Parameters
    ----------
    path : str

    Returns
    -------
    dict

    """
    files = [os.path.join(path, x) for x in os.listdir(path) \
             if os.path.splitext(x)[1] == ".toml"]
    assert len(files) == 1, "only 1 .toml file is currently supported"
    return load_data(files[0])


def update_pydss_controllers(project_path, scenario, controller_type, 
                             controller, dss_file):
    """Update a scenario's controllers from an OpenDSS file.

    Parameters
    ----------
    project_path : str
        pydss project path.
    scenario : str
        pydss scenario name in project.
    controller_type : str
        A type of pydss controler
    controller : str
        The controller name
    dss_file : str
        A DSS file path
    """
    if controller_type not in READ_CONTROLLER_FUNCTIONS:
        supported_types = list(READ_CONTROLLER_FUNCTIONS.keys())
        print(f"Invalid controller_type={controller_type}, supported: {supported_types}")
        sys.exit(1)

    sim_file = os.path.join(project_path, SIMULATION_SETTINGS_FILENAME)
    settings = load_simulation_settings(sim_file)
    if not settings.project.use_controller_registry:
        print(f"'Use Controller Registry' must be set to true in {sim_file}")
        sys.exit(1)

    registry = Registry()
    if not registry.is_controller_registered(controller_type, controller):
        print(f"{controller_type} / {controller} is not registered")
        sys.exit(1)

    data = {}
    filename = f"{project_path}/Scenarios/{scenario}/pyControllerList/{controller_type}.toml"
    if os.path.exists(filename):
        data = load_data(filename)
        for val in data.values():
            if not isinstance(val, list):
                print(f"{filename} has an invalid format")
                sys.exit(1)

    element_names = READ_CONTROLLER_FUNCTIONS[controller_type](dss_file)
    num_added = 0
    if controller in data:
        existing = set(data[controller])
        final = list(existing.union(set(element_names)))
        data[controller] = final
        num_added = len(final) - len(existing)
    else:
        data[controller] = element_names
        num_added = len(element_names)

    # Remove element_names from any other controllers.
    set_names = set(element_names)
    for _controller, values in data.items():
        if _controller != controller:
            final = set(values).difference_update(set_names)
            if final is None:
                final_list = None
            else:
                final_list = list(final)
            data[_controller] = final_list

    dump_data(data, filename)
    print(f"Added {num_added} names to {filename}")
