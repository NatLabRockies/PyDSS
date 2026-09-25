from pydss.common import PROFILE_MAPPING
import toml
import abc
import os

from pydss.simulation_input_models import SimulationSettingsModel


class BaseProfileManager(abc.ABC):
    def __init__(self, sim_instance, solver, settings: SimulationSettingsModel, logger, **kwargs):
        self.sim_instance = sim_instance
        self.settings = settings
        self.solver = solver
        self.logger = logger
        self.kwargs = kwargs
        if not settings.profiles.is_relative_path:
            self.basepath = settings.profiles.source
        else:
            self.basepath = os.path.join(
                settings.project.active_project_path,
                "Profiles",
                settings.profiles.source,
            )
        self.mapping_file = os.path.join(
            settings.project.active_project_path, "Profiles", PROFILE_MAPPING
        )
        self.Profiles = {}
        self.mapping = toml.load(open(self.mapping_file, "r"))
        self.sTime = None
        self.eTime = None
        self.simRes = None

    @abc.abstractmethod
    def setup_profiles(self):
        pass

    @abc.abstractmethod
    def update(self):
        pass


class BaseProfile(abc.ABC):
    def __init__(self, sim_instance, dataset, devices, solver, mapping_dict, logger, **kwargs):
        self.sim_instance = sim_instance
        self.mapping_dict = mapping_dict
        self.dataset = dataset
        self.devices = devices
        self.logger = logger
        self.solver = solver

    @abc.abstractmethod
    def update_profile_settings(self):
        pass

    @abc.abstractmethod
    def update(self):
        pass
