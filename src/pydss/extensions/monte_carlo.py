from ast import literal_eval
import os

from loguru import logger
from scipy import stats
import numpy as np

from pydss.simulation_input_models import SimulationSettingsModel
from pydss.utils import utils


class MonteCarloSim:
    def __init__(
        self,
        settings: SimulationSettingsModel,
        dss_paths,
        dss_objects,
        dss_objects_by_class,
    ):
        self.__dss_paths = dss_paths
        self.__dss_objects = dss_objects
        self._settings = settings
        self.__dss_objects_by_class = dss_objects_by_class

        try:
            mc_file = os.path.join(
                self._settings.project.active_scenario, "Monte_Carlo", "MonteCarloSettings.toml"
            )
            mc_file_path = os.path.join(self.__dss_paths["Import"], mc_file)

            logger.info("Reading monte carlo scenario settings file from " + mc_file_path)
            self.__mc_settings_dict = utils.load_data(mc_file_path)
        except:
            logger.error("Failed to read Monte Carlo scenario generation file %s", mc_file_path)
            raise
        return

    def create_scenario(self):
        for properties in self.__mc_settings_dict.values():
            if properties["Class"] in self.__dss_objects_by_class:
                elements = self.__dss_objects_by_class[properties["Class"]]
                element_names = list(elements.keys())
                if properties["useWildCard"]:
                    element_names = [x for x in element_names if properties["Wildcard"] in x]
                num_elements = len(element_names)
                distribution_params = literal_eval(properties["Parameters"])

                distribution = getattr(stats, properties["Distribution"].replace(" ", ""))
                if not properties["isList"]:
                    samples = distribution.rvs(*distribution_params, size=num_elements)
                    if properties["isInteger"]:
                        samples = [int(round(x)) for x in samples]
                    for element_name, value in zip(element_names, samples):
                        elements[element_name].SetParameter(properties["Property"], value)
                else:
                    samples = distribution.rvs(
                        *distribution_params, size=num_elements * properties["ListLength"]
                    )
                    if properties["isInteger"]:
                        samples = [int(round(x)) for x in samples]
                    samples = np.reshape(samples, (num_elements, properties["ListLength"]))
                    for element_name, value in zip(element_names, samples):
                        value = (
                            str(value)
                            .replace("\n", "")
                            .replace("\r", "")
                            .replace("[ ", "[")
                            .replace(" ]", "]")
                        )
                        elements[element_name].SetParameter(properties["Property"], value)
            else:
                logger.warning(properties["Class"] + " class not present in object dictionary.")
        return


MonteCarloSim.Create_Scenario = MonteCarloSim.create_scenario
