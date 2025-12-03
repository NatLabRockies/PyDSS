from pydss.common import SimulationType
from pydss.simulation_input_models import SimulationSettingsModel
from pydss.pyContrReader import read_controller_settings_from_registry
from pydss.dssElementFactory import create_dss_element
from pydss.utils.utils import make_human_readable_size
from pydss.pyContrReader import pyContrReader as pcr
from pydss.exceptions import (
    InvalidConfiguration, PyDssConvergenceError, PyDssConvergenceErrorCountExceeded,
    PyDssConvergenceMaxError, OpenDssModelError, OpenDssConvergenceErrorCountExceeded
)
from pydss.ProfileManager import ProfileInterface
from pydss.pyPostprocessor import pyPostprocess
import pydss.pyControllers as pyControllers
from pydss import helics_interface as HI
from pydss.ResultData import ResultData
from pydss.dssCircuit import dssCircuit
from pydss.common import SnapshotTimePointSelectionMode, DATE_FORMAT
from pydss.dssBus import dssBus
from pydss import SolveMode
from pydss.simulation_input_models import SimulationSettingsModel
from pydss.utils.simulation_utils import SimulationFilteredTimeRange
from pydss.utils.timing_utils import Timer, timer_stats_collector, track_timing
from pydss.get_snapshot_timepoints import get_snapshot_timepoint

import opendssdirect as dss
import numpy as np
from loguru import logger
import json
import time
import os
from collections import defaultdict
from pathlib import Path

from opendssdirect.utils import run_command

CONTROLLER_PRIORITIES = 3

class OpenDSS:
    def __init__(self, settings: SimulationSettingsModel):
        self._dssInstance = dss
        self._TempResultList = []
        self._dssBuses = {}
        self._dssObjects = {}
        self._dssObjectsByClass = {}
        self._DelFlag = 0
        self._settings = settings
        self._convergenceErrors = 0
        self._convergenceErrorsOpenDSS = 0
        self._maxConvergenceErrorCount = None
        self._maxConvergenceError = 0.0
        self._controller_iteration_counts = {}
        self._simulation_range = SimulationFilteredTimeRange.from_settings(settings)

        root_path = settings.project.project_path
        active_project_path = root_path / settings.project.active_project
        import_path = active_project_path / 'Scenarios'
        active_scenario_path = import_path / settings.project.active_scenario
        self._ActiveProject = settings.project.active_project

        self._dssPath = {
            'root': root_path,
            'Import': import_path,
            'ExportLists': active_scenario_path / 'ExportLists',
            'pyControllers': active_scenario_path / 'pyControllerList',
            'Export': active_project_path /  'Exports',
            'Log': active_project_path / 'Logs',
            'dssFiles': active_project_path / 'DSSfiles',
            'dssFilePath': active_project_path / 'DSSfiles' / settings.project.dss_file,
        }

        if settings.project.dss_file_absolute_path:
            self._dssPath['dssFilePath'] = Path(settings.project.dss_file)

        if not self._dssPath['dssFilePath'].exists():
            raise InvalidConfiguration(f"DSS file {self._dssPath['dssFilePath']} does not exist")

        logger.info('An instance of OpenDSS version ' + self._dssInstance.__version__ + ' has been created.')

        for key, path in self._dssPath.items():
            if path.name == "pyControllerList" and not path.exists():
                # This will happen if a zipped project with no controllers is unzipped and then run.
                path.mkdir()
            else:
                assert path.exists(), '{} path: {} does not exist!'.format(key, path)

        self._compile_model()

        logger.info('OpenDSS fundamental frequency set to :  ' + str(settings.frequency.fundamental_frequency) + ' Hz')

        #run_command('Set %SeriesRL={}'.format(settings.frequency.percentage_load_in_series))
        if settings.frequency.neglect_shunt_admittance:
            run_command('Set NeglectLoadY=Yes')

        active_scenario = self._GetActiveScenario()
        if active_scenario.snapshot_time_point_selection_config.mode != SnapshotTimePointSelectionMode.NONE:
            self._SetSnapshotTimePoint(active_scenario)

        self._dssCircuit = self._dssInstance.Circuit
        self._dssElement = self._dssInstance.Element
        self._dssBus = self._dssInstance.Bus
        self._dssClass = self._dssInstance.ActiveClass
        self._dssCommand = run_command
        self._dssSolution = self._dssInstance.Solution
        self._dssSolver = SolveMode.GetSolver(settings=settings, dssInstance=self._dssInstance)
        self._dssBuses = self.CreateBusObjects()
        self._dssObjects, self._dssObjectsByClass = self.CreateDssObjects(self._dssBuses)
        self._dssSolver.reSolve()

        if settings.profiles.use_profile_manager:
            #TODO: disable internal profiles
            logger.info('Disabling internal yearly and duty-cycle profiles.')
            for m in ["Loads", "PVSystem", "Generator", "Storage"]:
                run_command(f'BatchEdit {m}..* yearly=NONE duty=None')
            profileSettings = self._settings.profiles.settings
            profileSettings["objects"] = self._dssObjects
            self.profileStore = ProfileInterface.Create(
                self._dssInstance, self._dssSolver, self._settings, logger, **profileSettings
            )

        self.ResultContainer = ResultData(settings, self._dssPath,  self._dssObjects, self._dssObjectsByClass,
                                          self._dssBuses, self._dssSolver, self._dssCommand, self._dssInstance)

        if settings.project.use_controller_registry:
            ControllerList = read_controller_settings_from_registry(self._dssPath['pyControllers'])
        else:
            pyCtrlReader = pcr(self._dssPath['pyControllers'])
            ControllerList = pyCtrlReader.pyControllers

        if ControllerList is not None:
            self._CreateControllers(ControllerList)

        self._increment_flag = True
        if settings.helics.co_simulation_mode:
            self._heilcs_interface = HI.helics_interface(self._dssSolver, self._dssObjects, self._dssObjectsByClass, settings,
                                           self._dssPath)
        logger.info("Simulation initialization complete")
        return

    @track_timing(timer_stats_collector)
    def _compile_model(self):
        self._dssInstance.Basic.ClearAll()
        self._dssInstance.utils.run_command('Log=NO')
        run_command('Clear')
        logger.info('Loading OpenDSS model')
        reply = ""
        try:
            orig_dir = os.getcwd()
            reply = run_command('compile ' + str(self._dssPath['dssFilePath']))
        finally:
            os.chdir(orig_dir)

        logger.info('OpenDSS:  ' + reply)
        if reply != "":
            raise OpenDssModelError(f"Error compiling OpenDSS model: {reply}")

    def _CreateControllers(self, ControllerDict):
        self._pyControls = {}
        self._pyControls_types = {}
        # logger.info(f'self._dssObjects -> {self._dssObjects}')
        # os.system("PAUSE")
        for ControllerType, ElementsDict in ControllerDict.items():
            # logger.info(f'ControllerType -> {ControllerType}, ElementsDict -> {ElementsDict}')
            # os.system("PAUSE")
            for ElmName, SettingsDict in ElementsDict.items():
                Controller = pyControllers.pyController.Create(ElmName, ControllerType, SettingsDict, self._dssObjects,
                                                  self._dssInstance, self._dssSolver)
                if Controller != -1:
                    controller_name = 'Controller.' + ElmName
                    self._pyControls[controller_name] = Controller
                    class_name, element_name = Controller.ControlledElement().split(".")
                    if controller_name not in self._pyControls_types:
                        self._pyControls_types[controller_name] = class_name
                    logger.info('Created pyController -> Controller.' + ElmName)
        return

    def _update_controllers(self, Priority, Time, Iteration, UpdateResults):
        errors = []
        maxError = 0
        _pyControls_types = set(self._pyControls_types.values())

        for class_name in _pyControls_types:
            self._dssInstance.Basic.SetActiveClass(class_name)
            elm = self._dssInstance.ActiveClass.First()
            while elm:
                element_name = self._dssInstance.CktElement.Name()
                controller_name = 'Controller.' + element_name
                if controller_name in self._pyControls:
                    controller = self._pyControls[controller_name]
                    error = controller.Update(Priority, Time, UpdateResults)
                    maxError = error if error > maxError else maxError
                elm = self._dssInstance.ActiveClass.Next()
        return maxError < self._settings.project.error_tolerance, maxError

    @staticmethod
    def CreateBusObjects():
        dssBuses = {}
        BusNames = dss.Circuit.AllBusNames()
        dss.run_command('New  Fault.DEFAULT Bus1={} enabled=no r=0.01'.format(BusNames[0]))
        for BusName in BusNames:
            dss.Circuit.SetActiveBus(BusName)
            dssBuses[BusName] = dssBus()
        return dssBuses

    @staticmethod
    def CreateDssObjects(dssBuses):
        dssObjects = {}
        dssObjectsByClass = defaultdict(dict)

        InvalidSelection = ['Settings', 'ActiveClass', 'dss', 'utils', 'PDElements', 'XYCurves', 'Bus', 'Properties']
        # TODO: this causes a segmentation fault. Aadil says it may not be needed.
        #self._dssObjectsByClass={'LoadShape': self._get_relavent_object_dict('LoadShape')}
        # logger.info(f"dss.Circuit.AllElementNames()  -> {dss.Circuit.AllElementNames()}")
        # os.system("PAUSE")
        for ElmName in dss.Circuit.AllElementNames():
            Class, Name =  ElmName.split('.', 1)
            ClassName = Class + 's'
            dss.Circuit.SetActiveElement(ElmName)
            dssObjectsByClass[ClassName][ElmName] = create_dss_element(Class, Name)
            dssObjects[ElmName] = dssObjectsByClass[ClassName][ElmName]

        for ObjName in dssObjects.keys():
            ClassName = ObjName.split('.')[0] + 's'
            if ObjName not in dssObjectsByClass[Class]:
                dssObjectsByClass[Class][ObjName] = dssObjects[ObjName]

        dssObjects['Circuit.' + dss.Circuit.Name()] = dssCircuit()
        dssObjectsByClass['Circuits'] = {
            'Circuit.' + dss.Circuit.Name(): dssObjects['Circuit.' + dss.Circuit.Name()]
        }
        dssObjectsByClass['Buses'] = dssBuses

        return dssObjects, dssObjectsByClass

    def _get_relavent_object_dict(self, key):
        object_list = {}
        element_collection = getattr(self._dssInstance, key)
        element = element_collection.First()
        while element:
            fullName = self._dssInstance.Element.Name()
            object, name =  fullName.split('.', 1)
            object_list[fullName] = create_dss_element(object, name, self._dssInstance)
            element = element_collection.Next()
        return object_list

    @track_timing(timer_stats_collector)
    def RunStep(self, step, updateObjects=None):
        # updating parameters before simulation run
        if self._settings.logging.log_time_step_updates:
            logger.info(f'Pydss datetime - {self._dssSolver.GetDateTime()}')
            logger.info(f'OpenDSS time [h] - {self._dssSolver.GetOpenDSSTime()}')
        if self._settings.profiles.use_profile_manager:
            self.profileStore.update()

        if self._settings.helics.co_simulation_mode:
            # self._heilcs_interface.updateHelicsPublications()
            self._increment_flag, helics_time = self._heilcs_interface.request_time_increment()

        if self._settings.helics.co_simulation_mode:
            self._heilcs_interface.updateHelicsSubscriptions()
        else:
            if updateObjects:
                for object, params in updateObjects.items():
                    cl, name = object.split('.')
                    self._Modifier.Edit_Element(cl, name, params)
        
        # pydss_update_agian = "y"
        # while pydss_update_agian == "y":
        #     if self._settings.helics.co_simulation_mode:
        #         self._heilcs_interface.updateHelicsSubscriptions()
        #     else:
        #         if updateObjects:
        #             for object, params in updateObjects.items():
        #                 cl, name = object.split('.')
        #                 self._Modifier.Edit_Element(cl, name, params)
        #     pydss_update_agian = input('enter your pydss update command: ')

        # run simulation time step and get results
        time_step_has_converged = True
        if not self._settings.project.disable_pydss_controllers:
            with Timer(timer_stats_collector, "UpdateControllers"):
                for priority in range(CONTROLLER_PRIORITIES):
                    priority_has_converged = False
                    for i in range(self._settings.project.max_control_iterations):
                        has_converged, error = self._update_controllers(priority, step, i, UpdateResults=False)
                        logger.debug('Control Loop {} convergence error: {}'.format(priority, error))
                        logger.debug('Control Loop {} convergence @step {} '.format(priority, step))
                        if has_converged:
                            priority_has_converged = True
                            break
                        self._dssSolver.reSolve()
                    if i == 0:
                        # Don't track 0.
                        pass
                    elif i not in self._controller_iteration_counts:
                        self._controller_iteration_counts[i] = 1
                    else:
                        self._controller_iteration_counts[i] += 1
                    if not priority_has_converged:
                        time_step_has_converged = False
                        logger.warning('Control Loop {} no convergence @ {} '.format(priority, step))
                        self._HandleConvergenceErrorChecks(step, error)


        if self._settings.frequency.enable_frequency_sweep and \
                self._settings.project.simulation_type != SimulationType.DYNAMIC:
            self._dssSolver.setMode('Harmonic')
            for frequency in np.arange(self._settings.frequency.start_frequency,
                                      self._settings.frequency.end_frequency + 1,
                                      self._settings.frequency.frequency_increment):
                self._dssSolver.setFrequency(frequency * self._settings.frequency.fundamental_frequency)
                self._dssSolver.reSolve()
                if self._settings.exports.export_results:
                    self.ResultContainer.UpdateResults()
            if self._settings.project.simulation_type != SimulationType.SNAPSHOT:
                self._dssSolver.setMode('Snapshot')
            else:
                self._dssSolver.setMode('Yearly')

        if self._settings.helics.co_simulation_mode:
            self._heilcs_interface.updateHelicsPublications()
            # if step < 1:
            #     self._increment_flag, helics_time = self._heilcs_interface.request_time_increment_2()
        # os.system("PAUSE")
        return time_step_has_converged

    def _HandleConvergenceErrorChecks(self, step, error):
        self._convergenceErrors += 1

        if self._maxConvergenceError != 0.0 and error > self._maxConvergenceError:
            logger.error("Convergence error %s exceeded max value %s at step %s", error, self._maxConvergenceError, step)
            raise PyDssConvergenceMaxError(f"Exceeded max convergence error {error}")

        if self._maxConvergenceErrorCount is not None and self._convergenceErrors > self._maxConvergenceErrorCount:
            logger.error("Exceeded convergence error count threshold at step %s", step)
            raise PyDssConvergenceErrorCountExceeded(f"{self._convergenceErrors} errors occurred")

    def _HandleOpenDSSConvergenceErrorChecks(self, step):
        self._convergenceErrorsOpenDSS += 1

        if self._maxConvergenceErrorCount is not None and self._convergenceErrorsOpenDSS > self._maxConvergenceErrorCount:
            logger.error(f"Exceeded OpenDSS convergence error count threshold at step {step}")
            raise OpenDssConvergenceErrorCountExceeded(f"{self._convergenceErrorsOpenDSS} errors occurred")

    def DryRunSimulation(self, project, scenario):
        """Run one time point for getting estimated space."""
        if not self._settings.exports.export_results:
            raise InvalidConfiguration("Log Reults must set to be True.")

        Steps, _, _ = self._dssSolver.SimulationSteps()
        logger.info('Dry run simulation...')
        self.ResultContainer.InitializeDataStore(project.hdf_store, Steps)

        try:
            self.RunStep(0)
            self.ResultContainer.UpdateResults()
        finally:
            self.ResultContainer.Close()

        return self.ResultContainer.max_num_bytes()

    def initStore(self, hdf_store, Steps, MC_scenario_number=None):
        self.ResultContainer.InitializeDataStore(hdf_store, Steps, MC_scenario_number)

    def RunSimulation(self, project, scenario, MC_scenario_number=None):
        """Yields a tuple of the results of each step.

        Yields
        ------
        tuple
            is_complete, step, has_converged, results

        """
        startTime = time.time()
        Steps, sTime, eTime = self._dssSolver.SimulationSteps()
        threshold = self._settings.project.convergence_error_percent_threshold
        if threshold > 0:
            self._maxConvergenceErrorCount = round(threshold * .01 * Steps)
        self._maxConvergenceError = self._settings.project.max_error_tolerance
        dss.Solution.Convergence(self._settings.project.error_tolerance)
        logger.info('Running simulation from {} till {}.'.format(sTime, eTime))
        logger.info('Simulation time step {}.'.format(Steps))
        logger.info(f"Set OpenDSS convergence to {dss.Solution.Convergence()}")
        logger.info('Max convergence error count {}.'.format(self._maxConvergenceErrorCount))
        logger.info("initializing store")
        self.ResultContainer.InitializeDataStore(project.hdf_store, Steps, MC_scenario_number)
        postprocessors = [
            pyPostprocess.Create(
                project,
                scenario,
                ppInfo,
                self._dssInstance,
                self._dssSolver,
                self._dssObjects,
                self._dssObjectsByClass,
                self._settings,
                logger,
            ) for ppInfo in scenario.post_process_infos
        ]
        if not postprocessors:
            logger.info('No post processing script selected')

        is_complete = False
        step = 0
        has_converged = False
        current_results = {}
        try:
            while step < Steps:
                pydss_has_converged = True
                opendss_has_converged = True
                within_range = self._simulation_range.is_within_range(self._dssSolver.GetDateTime())
                if within_range:
                    pydss_has_converged = self.RunStep(step)
                    # logger.info(f'Finish simulation: step {step} 1')
                    # pydss_has_converged = self.RunStep(step)
                    # logger.info(f'Finish simulation: step {step} 2')
                    # pydss_has_converged = self.RunStep(step)
                    # logger.info(f'Finish simulation: step {step} 3')
                    opendss_has_converged = dss.Solution.Converged()
                    if not opendss_has_converged:
                        logger.error(f"OpenDSS did not converge at step={step} pydss_converged={pydss_has_converged}")
                        self._HandleOpenDSSConvergenceErrorChecks(step)
                
                if pydss_has_converged:
                    has_converged = True
                else:
                    has_converged = pydss_has_converged and opendss_has_converged
                
                if step == 0 and self.ResultContainer is not None:
                    size = make_human_readable_size(self.ResultContainer.max_num_bytes())
                    logger.info('Storage requirement estimation: %s, estimated based on first time step run.', size)
                if postprocessors and within_range:
                    step, has_converged = self._RunPostProcessors(step, Steps, postprocessors)
                if self._increment_flag:
                    step += 1
                    # if step < 1:
                    #     step += 1
                    # else:
                    #     step += 2

                # In the case of a frequency sweep, the code updates results at each frequency.
                # Doing so again would cause a duplicate result.
                if (
                    self._settings.exports.export_results and not
                    (self._settings.frequency.enable_frequency_sweep and \
                     self._settings.project.simulation_type != SimulationType.DYNAMIC)
                ):
                    store_nan = (
                        not within_range or
                        (not has_converged and
                         self._settings.project.skip_export_on_convergence_error)
                    )
                    self.ResultContainer.UpdateResults(store_nan=store_nan)

                if self._settings.helics.co_simulation_mode:
                    if self._increment_flag:
                        self._dssSolver.IncStep()
                    else:
                        self._dssSolver.reSolve()
                else:
                    self._dssSolver.IncStep()

                if self._settings.exports.export_results:
                    current_results = self.ResultContainer.CurrentResults
                yield False, step, has_converged, current_results

        finally:
            if self._settings and self._settings.exports.export_results:
                # This is here to guarantee that DatasetBuffers aren't left
                # with any data in memory.
                self.ResultContainer.Close()

            for postprocessor in postprocessors:
                postprocessor.finalize()

        if self._settings and self._settings.exports.export_results:
            self.ResultContainer.ExportResults()

        timer_stats_collector.log_stats(clear=True)
        if self._controller_iteration_counts:
            data = {
                "Report": "ControllerIterationCounts",
                "Scenario": self._settings.project.active_scenario,
                "Counts": self._controller_iteration_counts,
            }
        
        logger.info(f'Simulation completed in { time.time() - startTime} seconds',)
        logger.info('End of simulation')
        yield True, step, has_converged, current_results

    def _RunPostProcessors(self, step, Steps, postprocessors):
        for postprocessor in postprocessors:
            orig_step = step
            step, has_converged, error = postprocessor.run(step, Steps, simulation=self)
            assert step <= orig_step, "step cannot increment in postprocessor"
            if not has_converged:
                name = postprocessor.__class__.__name__
                logger.warn("postprocessor %s reported a convergence error at step %s", name, step)
                self._HandleConvergenceErrorChecks(step, error)

        return step, has_converged

    def RunMCsimulation(self, project, scenario, samples):
        from pydss.Extensions.MonteCarlo import MonteCarloSim
        MC = MonteCarloSim(self._settings, self._dssPath, self._dssObjects, self._dssObjectsByClass)
        for i in range(samples):
            MC.Create_Scenario()
            for is_complete, _, _, _ in self.RunSimulation(project, scenario, i):
                if is_complete:
                    break
        return

    def _GetActiveScenario(self):
        active_scenario = self._settings.project.active_scenario
        for scenario in self._settings.project.scenarios:
            if scenario.name == active_scenario:
                return scenario
        raise InvalidConfiguration(f"Active Scenario {active_scenario} is not present")

    @track_timing(timer_stats_collector)
    def _SetSnapshotTimePoint(self, scenario):
        """Adjusts the time parameters based on the mode."""
        p_settings = self._settings.project
        config = scenario.snapshot_time_point_selection_config
        mode = config.mode
        assert mode != SnapshotTimePointSelectionMode.NONE, mode

        if mode != SnapshotTimePointSelectionMode.NONE:
            if p_settings.simulation_type != SimulationType.QSTS:
                raise InvalidConfiguration(f"{mode} is only supported with QSTS simulations")

            # These settings have to be temporarily overridden because of the underlying
            # implementation to create a load shape dataframes..
            orig_start = p_settings.start_time
            orig_duration = p_settings.simulation_duration_min
            if orig_duration != p_settings.step_resolution_sec / 60:
                raise InvalidConfiguration("Simulation duration must be the same as resolution")
            try:
                p_settings.start_time = config.start_time
                p_settings.simulation_duration_min = config.search_duration_min
                new_start = get_snapshot_timepoint(self._settings, mode).strftime(DATE_FORMAT)
                p_settings.start_time = new_start
                logger.info("Changed simulation start time from %s to %s",
                    orig_start,
                    new_start,
                )
            except Exception:
                p_settings.start_time = orig_start
                raise
            finally:
                p_settings.simulation_duration_min = orig_duration
        else:
            assert False, f"unsupported mode {mode}"

    # def __del__(self):
    #     logger.info('An instance of OpenDSS (' + str(self) + ') has been deleted.')
    #     loggers = [logger, self._reportsLogger]
    #     if self._settings["Logging"]["Log to external file"]:
    #         for L in loggers:
    #             handlers = list(L.handlers)
    #             for filehandler in handlers:
    #                 filehandler.flush()
    #                 filehandler.close()
    #                 L.removeHandler(filehandler)
    #     return
