import abc
import os

from pydss.exceptions import InvalidParameter
from pydss.utils.utils import load_data


class AbstractPostprocess(abc.ABC):
    """An abstract class that serves as template for all pyPlot classes in :mod:`pydss.pyPlots.Plots` module.

    :param project: A :class:`pydss.pydss_project.PyDssProject` object representing a project
    :type project: PyDssProject
    :param scenario: A :class:`pydss.pydss_project.PyDssScenario` object representing a scenario
    :type scenario: PyDssScenario
    :param inputs: user inputs
    :type inputs: dict
    :param dssInstance: A :class:`pydss.dss_element.DssElement` object that wraps around an OpenDSS 'Fault' element
    :type dssInstance: dict
    :param dssBuses: Dictionary of all :class:`pydss.dss_bus.DssBus` objects in pydss
    :type dssBuses: dict of :class:`pydss.dss_bus.DssBus` objects
    :param dssObjects: Dictionary of all :class:`pydss.dss_element.DssElement` objects in pydss
    :type dssObjects: dict of :class:`pydss.dss_element.DssElement` objects
    :param dssObjectsByClass:  Dictionary of all :class:`pydss.dss_element.DssElement` objects in pydss sorted by class
    :type dssObjectsByClass: dict of :class:`pydss.dss_element.DssElement` objects
    :param dssSolver: An instance of one of the classes defined in :mod:`pydss.solve_mode`.
    :type dssSolver: :mod:`pydss.solve_mode`

    """

    def __init__(
        self,
        project,
        scenario,
        inputs,
        dss_instance,
        dss_solver,
        dss_objects,
        dss_objects_by_class,
        simulation_settings,
        logger,
    ):
        """This is the constructor class."""
        self.project = project
        self.scenario = scenario
        if inputs.config_file == "":
            self.config = {}
        else:
            self.config = load_data(inputs.config_file)
        self.config["Outputs"] = project.get_post_process_directory(scenario.name)
        os.makedirs(self.config["Outputs"], exist_ok=True)
        self.Settings = simulation_settings

        self._dssInstance = dss_instance
        self.logger = logger
        self._check_input_fields()

    @abc.abstractmethod
    def run(self, step, step_max, simulation=None):
        """Method used to run a post processing script.

        Parameters
        ----------
        step : int
            Current step
        stepMax : int
            Last step of the simulation
        simulation : OpenDSS
            pydss simulation control class. Provided for access to control algorithms.
            Subclasses should not hold references to this instance after this method exits.

        """

    @abc.abstractmethod
    def _get_required_input_fields(self):
        """Return the required input fields."""

    @abc.abstractmethod
    def finalize(self):
        """Method used to combine post processing results from all steps."""

    def _check_input_fields(self):
        required_fields = self._get_required_input_fields()
        fields = set(self.config.keys())
        for field in required_fields:
            if field not in fields:
                raise InvalidParameter(f"{self.__class__.__name__} requires input field {field}")
