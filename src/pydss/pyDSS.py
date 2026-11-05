import pydss
import os

from loguru import logger

from pydss.common import RUN_SIMULATION_FILENAME
from pydss.exceptions import InvalidConfiguration
from pydss.dssInstance import OpenDSS
from pydss.simulation_input_models import SimulationSettingsModel, dump_settings
from pydss.utils.utils import dump_data, load_data

PYDSS_BASE_DIR = os.path.join(os.path.dirname(getattr(pydss, "__path__")[0]), "pydss")

class instance(object):

    def __init__(self):
        self._estimated_space = None

    def run(self, settings: SimulationSettingsModel, project, scenario, dry_run=False):
        
        self.run_scenario(
            project,
            scenario,
            settings,
            dry_run=dry_run,
        )
        return

    def create_dss_instance(self, dss_args):
        return OpenDSS(dss_args)

    def run_scenario(self, project, scenario, settings: SimulationSettingsModel, dry_run=False):
        if dry_run:
            dss = OpenDSS(settings)
            self._dump_scenario_simulation_settings(settings)
            #dss.init(dss_args)
            logger.info('Dry run scenario: %s', settings.project.active_scenario)
            if settings.monte_carlo.num_scenarios > 0:
                raise InvalidConfiguration("Dry run does not support MonteCarlo simulation.")
            else:
                self._estimated_space = dss.DryRunSimulation(project, scenario)
            return None, None

        opendss = OpenDSS(settings)
        self._dump_scenario_simulation_settings(settings)
        logger.info(f'Running scenario: {settings.project.active_scenario}')
        if settings.monte_carlo.num_scenarios > 0:
            opendss.RunMCsimulation(project, scenario, samples=settings.monte_carlo.num_scenarios)
        else:
            for is_complete, _, _, _ in opendss.RunSimulation(project, scenario):
                if is_complete:
                    break

    def get_estimated_space(self):
        return self._estimated_space

    def _dump_scenario_simulation_settings(self, settings: SimulationSettingsModel):
        # Various settings may have been updated. Write the actual settings to a file.
        scenario_simulation_filename = os.path.join(
            settings.project.project_path,
            settings.project.active_project,
            "Scenarios",
            settings.project.active_scenario,
            RUN_SIMULATION_FILENAME,
        )
        dump_settings(settings, scenario_simulation_filename)
