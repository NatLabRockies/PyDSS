from pydss.common import SimulationType
from pydss.simulation_input_models import SimulationSettingsModel
from pydss.py_contr_reader import read_controller_settings_from_registry
from pydss.dss_element_factory import create_dss_element
from pydss.utils.utils import make_human_readable_size
from pydss.py_contr_reader import PyContrReader
from pydss.exceptions import (
    InvalidConfiguration,
    PyDssConvergenceErrorCountExceeded,
    PyDssConvergenceMaxError,
    OpenDssModelError,
    OpenDssConvergenceErrorCountExceeded,
)
from pydss.profile_manager import profile_interface
from pydss.py_postprocessor import py_postprocess
from pydss.py_controllers import py_controller
from pydss.helics_interface import HelicsInterface
from pydss.result_data import ResultData
from pydss.dss_circuit import DssCircuit
from pydss.common import SnapshotTimePointSelectionMode, DATE_FORMAT
from pydss.dss_bus import DssBus
from pydss import solve_mode
from pydss.utils.simulation_utils import SimulationFilteredTimeRange
from pydss.utils.timing_utils import timer_stats_collector, track_timing
from pydss.get_snapshot_timepoints import get_snapshot_timepoint
from pydss.openmdao_components import (
    CircuitExplicitComponent,
    OpenDSSCircuitAdapter,
    VariableSpec,
)
from pydss.openmdao_model import build_openmdao_problem, controller_circuit_variable

import opendssdirect as dss
import openmdao.api as om
import numpy as np
from loguru import logger
import time
import os
from collections import defaultdict
from pathlib import Path

from opendssdirect.utils import run_command


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
        import_path = active_project_path / "Scenarios"
        active_scenario_path = import_path / settings.project.active_scenario
        self._ActiveProject = settings.project.active_project

        self._dssPath = {
            "root": root_path,
            "Import": import_path,
            "ExportLists": active_scenario_path / "ExportLists",
            "py_controllers": active_scenario_path / "pyControllerList",
            "Export": active_project_path / "Exports",
            "Log": active_project_path / "Logs",
            "dssFiles": active_project_path / "DSSfiles",
            "dssFilePath": active_project_path / "DSSfiles" / settings.project.dss_file,
        }

        if settings.project.dss_file_absolute_path:
            self._dssPath["dssFilePath"] = Path(settings.project.dss_file)

        if not self._dssPath["dssFilePath"].exists():
            raise InvalidConfiguration(f"DSS file {self._dssPath['dssFilePath']} does not exist")

        logger.info(
            "An instance of OpenDSS version " + self._dssInstance.__version__ + " has been created."
        )

        for key, path in self._dssPath.items():
            if path.name == "pyControllerList" and not path.exists():
                # This will happen if a zipped project with no controllers is unzipped and then run.
                path.mkdir()
            else:
                assert path.exists(), "{} path: {} does not exist!".format(key, path)

        self._compile_model()

        logger.info(
            "OpenDSS fundamental frequency set to :  "
            + str(settings.frequency.fundamental_frequency)
            + " Hz"
        )

        # run_command('Set %SeriesRL={}'.format(settings.frequency.percentage_load_in_series))
        if settings.frequency.neglect_shunt_admittance:
            run_command("Set NeglectLoadY=Yes")

        active_scenario = self._GetActiveScenario()
        if (
            active_scenario.snapshot_time_point_selection_config.mode
            != SnapshotTimePointSelectionMode.NONE
        ):
            self._SetSnapshotTimePoint(active_scenario)

        self._dssCircuit = self._dssInstance.Circuit
        self._dssElement = self._dssInstance.Element
        self._dssBus = self._dssInstance.Bus
        self._dssClass = self._dssInstance.ActiveClass
        self._dssCommand = run_command
        self._dssSolution = self._dssInstance.Solution
        self._dssSolver = solve_mode.get_solver(settings=settings, dss_instance=self._dssInstance)
        self._dssBuses = self.create_bus_objects()
        self._dssObjects, self._dssObjectsByClass = self.create_dss_objects(self._dssBuses)
        self._dssSolver.reSolve()

        if settings.profiles.use_profile_manager:
            # TODO: disable internal profiles
            logger.info("Disabling internal yearly and duty-cycle profiles.")
            for m in ["Loads", "PVSystem", "Generator", "Storage"]:
                run_command(f"BatchEdit {m}..* yearly=NONE duty=None")
            profile_settings = self._settings.profiles.settings
            profile_settings["objects"] = self._dssObjects
            self.profileStore = profile_interface.create(
                self._dssInstance, self._dssSolver, self._settings, logger, **profile_settings
            )

        self.ResultContainer = ResultData(
            settings,
            self._dssPath,
            self._dssObjects,
            self._dssObjectsByClass,
            self._dssBuses,
            self._dssSolver,
            self._dssCommand,
            self._dssInstance,
        )

        if settings.project.use_controller_registry:
            controller_list = read_controller_settings_from_registry(
                self._dssPath["py_controllers"]
            )
        else:
            py_ctrl_reader = PyContrReader(self._dssPath["py_controllers"])
            controller_list = py_ctrl_reader.pyControllers

        if controller_list is not None:
            self._create_controllers(controller_list)

        self._openmdao_problem = None
        self._openmdao_adapter = None
        if getattr(self, "_pyControls", None):
            self._setup_openmdao_problem()

        self._increment_flag = True
        if settings.helics.co_simulation_mode:
            self._heilcs_interface = HelicsInterface(
                self._dssSolver, self._dssObjects, self._dssObjectsByClass, settings, self._dssPath
            )
        logger.info("Simulation initialization complete")
        return

    @track_timing(timer_stats_collector)
    def _compile_model(self):
        self._dssInstance.Basic.ClearAll()
        self._dssInstance.utils.run_command("Log=NO")
        run_command("Clear")
        logger.info("Loading OpenDSS model")
        reply = ""
        try:
            orig_dir = os.getcwd()
            reply = run_command("compile " + str(self._dssPath["dssFilePath"]))
        finally:
            os.chdir(orig_dir)

        logger.info("OpenDSS:  " + reply)
        if reply != "":
            raise OpenDssModelError(f"Error compiling OpenDSS model: {reply}")

    def _create_controllers(self, controller_dict):
        self._pyControls = {}
        for controller_type, elements_dict in controller_dict.items():
            for element_name, settings_dict in elements_dict.items():
                self._pyControls[element_name] = py_controller.create(
                    controller_type, settings_dict, element_name=element_name
                )
                logger.info("Created OpenMDAO controller -> Controller." + element_name)
        return

    def _setup_openmdao_problem(self):
        controller_items = sorted(self._pyControls.items())
        elements = {name: self._dssObjects[name] for name, _ in controller_items}
        command_specs = []
        measurement_specs = []
        command_map = {}
        measurement_map = {}
        controllers = []
        connections = []

        for index, (element_name, controller) in enumerate(controller_items):
            subsystem_name = f"controller_{index}"
            controllers.append((subsystem_name, controller))
            element_class = element_name.split(".", 1)[0]
            if element_class.lower() == "pvsystem":
                controller.options["rated_kva"] = float(elements[element_name].get_parameter("kVA"))
            parameter_map = controller.command_parameters(element_class)
            for spec in controller.output_specs():
                if spec.name.startswith("command_"):
                    circuit_name = controller_circuit_variable(index, spec.name)
                    command_specs.append(
                        VariableSpec(circuit_name, spec.shape, spec.units, spec.val)
                    )
                    parameter = parameter_map[spec.name]
                    command_map[circuit_name] = (element_name, parameter)
                    connections.append((f"{subsystem_name}.{spec.name}", f"circuit.{circuit_name}"))
            for spec in controller.input_specs():
                circuit_name = controller_circuit_variable(index, spec.name)
                measurement_specs.append(
                    VariableSpec(circuit_name, spec.shape, spec.units, spec.val)
                )
                measurement_map[circuit_name] = (element_name, spec.name)
                connections.append((f"circuit.{circuit_name}", f"{subsystem_name}.{spec.name}"))

        self._openmdao_adapter = OpenDSSCircuitAdapter(
            self._dssInstance, self._dssSolver, elements, command_map, measurement_map
        )
        circuit = CircuitExplicitComponent(
            adapter=self._openmdao_adapter,
            command_specs=tuple(command_specs),
            measurement_specs=tuple(measurement_specs),
        )
        reports_enabled = (
            self._settings.project.openmdao_reports and "PYTEST_CURRENT_TEST" not in os.environ
        )
        self._openmdao_problem = build_openmdao_problem(
            circuit,
            controllers,
            connections,
            max_iterations=self._settings.project.max_control_iterations,
            tolerance=self._settings.project.error_tolerance,
            reports=reports_enabled,
            work_dir=(
                self._dssPath["dssFiles"].parent / "OpenMDAOReports" if reports_enabled else None
            ),
            name=self._ActiveProject,
        )

    @staticmethod
    def create_bus_objects():
        dss_buses = {}
        bus_names = dss.Circuit.AllBusNames()
        dss.run_command("New  Fault.DEFAULT Bus1={} enabled=no r=0.01".format(bus_names[0]))
        for bus_name in bus_names:
            dss.Circuit.SetActiveBus(bus_name)
            dss_buses[bus_name] = DssBus()
        return dss_buses

    @staticmethod
    def create_dss_objects(dss_buses):
        dss_objects = {}
        dss_objects_by_class = defaultdict(dict)

        # TODO: this causes a segmentation fault. Aadil says it may not be needed.
        # self._dssObjectsByClass={'LoadShape': self._get_relavent_object_dict('LoadShape')}

        for element_name in dss.Circuit.AllElementNames():
            class_name, object_name = element_name.split(".", 1)
            class_name = class_name + "s"
            dss.Circuit.SetActiveElement(element_name)
            dss_objects_by_class[class_name][element_name] = create_dss_element(
                class_name, object_name
            )
            dss_objects[element_name] = dss_objects_by_class[class_name][element_name]

        for object_name in dss_objects.keys():
            class_name = object_name.split(".")[0] + "s"
            if object_name not in dss_objects_by_class[class_name]:
                dss_objects_by_class[class_name][object_name] = dss_objects[object_name]

        dss_objects["Circuit." + dss.Circuit.Name()] = DssCircuit()
        dss_objects_by_class["Circuits"] = {
            "Circuit." + dss.Circuit.Name(): dss_objects["Circuit." + dss.Circuit.Name()]
        }
        dss_objects_by_class["Buses"] = dss_buses

        return dss_objects, dss_objects_by_class

    def _get_relavent_object_dict(self, key):
        object_list = {}
        element_collection = getattr(self._dssInstance, key)
        element = element_collection.First()
        while element:
            full_name = self._dssInstance.Element.Name()
            object, name = full_name.split(".", 1)
            object_list[full_name] = create_dss_element(object, name, self._dssInstance)
            element = element_collection.Next()
        return object_list

    @track_timing(timer_stats_collector)
    def run_step(self, step, update_objects=None):
        # updating parameters before simulation run
        if self._settings.logging.log_time_step_updates:
            logger.info(f"Pydss datetime - {self._dssSolver.GetDateTime()}")
            logger.info(f"OpenDSS time [h] - {self._dssSolver.GetOpenDSSTime()}")
        if self._settings.profiles.use_profile_manager:
            self.profileStore.update()

        if self._settings.helics.co_simulation_mode:
            self._heilcs_interface.update_helics_subscriptions()
        else:
            if update_objects:
                for object, params in update_objects.items():
                    cl, name = object.split(".")
                    self._Modifier.Edit_Element(cl, name, params)

        # run simulation time step and get results
        time_step_has_converged = True
        if self._openmdao_problem is not None:
            self._openmdao_adapter.set_time(step * self._settings.project.step_resolution_sec)
            self._openmdao_problem.model.reset_step()
            try:
                self._openmdao_problem.run_model()
            except om.AnalysisError as exc:
                logger.warning("OpenMDAO time step {} did not converge: {}", step, exc)
                self._handle_convergence_error_checks(step, float("inf"))
                time_step_has_converged = False
            else:
                self._openmdao_problem.model.commit_step()

        if (
            self._settings.frequency.enable_frequency_sweep
            and self._settings.project.simulation_type != SimulationType.DYNAMIC
        ):
            self._dssSolver.setMode("Harmonic")
            for frequency in np.arange(
                self._settings.frequency.start_frequency,
                self._settings.frequency.end_frequency + 1,
                self._settings.frequency.frequency_increment,
            ):
                self._dssSolver.setFrequency(
                    frequency * self._settings.frequency.fundamental_frequency
                )
                self._dssSolver.reSolve()
                if self._settings.exports.export_results:
                    self.ResultContainer.update_results()
            if self._settings.project.simulation_type != SimulationType.SNAPSHOT:
                self._dssSolver.setMode("Snapshot")
            else:
                self._dssSolver.setMode("Yearly")

        if self._settings.helics.co_simulation_mode:
            self._heilcs_interface.update_helics_publications()
            self._increment_flag, helics_time = self._heilcs_interface.request_time_increment()

        return time_step_has_converged

    def _handle_convergence_error_checks(self, step, error):
        self._convergenceErrors += 1

        if self._maxConvergenceError != 0.0 and error > self._maxConvergenceError:
            logger.error(
                "Convergence error %s exceeded max value %s at step %s",
                error,
                self._maxConvergenceError,
                step,
            )
            raise PyDssConvergenceMaxError(f"Exceeded max convergence error {error}")

        if (
            self._maxConvergenceErrorCount is not None
            and self._convergenceErrors > self._maxConvergenceErrorCount
        ):
            logger.error("Exceeded convergence error count threshold at step %s", step)
            raise PyDssConvergenceErrorCountExceeded(f"{self._convergenceErrors} errors occurred")

    def _handle_opendss_convergence_error_checks(self, step):
        self._convergenceErrorsOpenDSS += 1

        if (
            self._maxConvergenceErrorCount is not None
            and self._convergenceErrorsOpenDSS > self._maxConvergenceErrorCount
        ):
            logger.error("Exceeded OpenDSS convergence error count threshold at step %s", step)
            raise OpenDssConvergenceErrorCountExceeded(
                f"{self._convergenceErrorsOpenDSS} errors occurred"
            )

    def dry_run_simulation(self, project, scenario):
        """Run one time point for getting estimated space."""
        if not self._settings.exports.export_results:
            raise InvalidConfiguration("Log Reults must set to be True.")

        steps, _, _ = self._dssSolver.SimulationSteps()
        logger.info("Dry run simulation...")
        self.ResultContainer.initialize_data_store(project.hdf_store, steps)

        try:
            self.run_step(0)
            self.ResultContainer.update_results()
        finally:
            self.ResultContainer.close()

        return self.ResultContainer.max_num_bytes()

    def init_store(self, hdf_store, steps, mc_scenario_number=None):
        self.ResultContainer.initialize_data_store(hdf_store, steps, mc_scenario_number)

    def run_simulation(self, project, scenario, mc_scenario_number=None):
        """Yields a tuple of the results of each step.

        Yields
        ------
        tuple
            is_complete, step, has_converged, results

        """
        elapsed_start_time = time.time()
        steps, simulation_start_time, simulation_end_time = self._dssSolver.SimulationSteps()
        threshold = self._settings.project.convergence_error_percent_threshold
        if threshold > 0:
            self._maxConvergenceErrorCount = round(threshold * 0.01 * steps)
        self._maxConvergenceError = self._settings.project.max_error_tolerance
        dss.Solution.Convergence(self._settings.project.error_tolerance)
        logger.info(
            "Running simulation from {} till {}.".format(simulation_start_time, simulation_end_time)
        )
        logger.info("Simulation time step {}.".format(steps))
        logger.info("Set OpenDSS convergence to %s", dss.Solution.Convergence())
        logger.info("Max convergence error count {}.".format(self._maxConvergenceErrorCount))
        logger.info("initializing store")
        self.ResultContainer.initialize_data_store(project.hdf_store, steps, mc_scenario_number)
        postprocessors = [
            py_postprocess.create(
                project,
                scenario,
                ppInfo,
                self._dssInstance,
                self._dssSolver,
                self._dssObjects,
                self._dssObjectsByClass,
                self._settings,
                logger,
            )
            for ppInfo in scenario.post_process_infos
        ]
        if not postprocessors:
            logger.info("No post processing script selected")

        step = 0
        has_converged = False
        current_results = {}
        try:
            while step < steps:
                pydss_has_converged = True
                opendss_has_converged = True
                within_range = self._simulation_range.is_within_range(self._dssSolver.GetDateTime())
                if within_range:
                    pydss_has_converged = self.run_step(step)
                    opendss_has_converged = dss.Solution.Converged()
                    if not opendss_has_converged:
                        logger.error(
                            "OpenDSS did not converge at step=%s pydss_converged=%s",
                            step,
                            pydss_has_converged,
                        )
                        self._handle_opendss_convergence_error_checks(step)
                has_converged = pydss_has_converged and opendss_has_converged
                if step == 0 and self.ResultContainer is not None:
                    size = make_human_readable_size(self.ResultContainer.max_num_bytes())
                    logger.info(
                        "Storage requirement estimation: %s, estimated based on first time step run.",
                        size,
                    )
                if postprocessors and within_range:
                    step, has_converged = self._RunPostProcessors(step, steps, postprocessors)
                if self._increment_flag:
                    step += 1

                # In the case of a frequency sweep, the code updates results at each frequency.
                # Doing so again would cause a duplicate result.
                if self._settings.exports.export_results and not (
                    self._settings.frequency.enable_frequency_sweep
                    and self._settings.project.simulation_type != SimulationType.DYNAMIC
                ):
                    store_nan = not within_range or (
                        not has_converged
                        and self._settings.project.skip_export_on_convergence_error
                    )
                    self.ResultContainer.update_results(store_nan=store_nan)

                if self._settings.helics.co_simulation_mode:
                    if self._increment_flag:
                        self._dssSolver.IncStep()
                    else:
                        self._dssSolver.reSolve()
                else:
                    self._dssSolver.IncStep()

                if self._settings.exports.export_results:
                    current_results = self.ResultContainer.current_results
                yield False, step, has_converged, current_results

        finally:
            if self._settings and self._settings.exports.export_results:
                # This is here to guarantee that DatasetBuffers aren't left
                # with any data in memory.
                self.ResultContainer.close()

            for postprocessor in postprocessors:
                postprocessor.finalize()

        if self._settings and self._settings.exports.export_results:
            self.ResultContainer.export_results()

        timer_stats_collector.log_stats(clear=True)
        if self._controller_iteration_counts:
            pass

        logger.info(
            f"Simulation completed in {time.time() - elapsed_start_time} seconds",
        )
        logger.info("End of simulation")
        yield True, step, has_converged, current_results

    def _run_post_processors(self, step, steps, postprocessors):
        for postprocessor in postprocessors:
            orig_step = step
            step, has_converged, error = postprocessor.run(step, steps, simulation=self)
            assert step <= orig_step, "step cannot increment in postprocessor"
            if not has_converged:
                name = postprocessor.__class__.__name__
                logger.warn("postprocessor %s reported a convergence error at step %s", name, step)
                self._handle_convergence_error_checks(step, error)

        return step, has_converged

    def run_mc_simulation(self, project, scenario, samples):
        from pydss.extensions.monte_carlo import MonteCarloSim

        monte_carlo = MonteCarloSim(
            self._settings, self._dssPath, self._dssObjects, self._dssObjectsByClass
        )
        for i in range(samples):
            monte_carlo.create_scenario()
            if i:
                # Each completed sample closes its metric buffers. Rebuild them so the
                # next HDF scenario group receives the full exported element datasets.
                self.ResultContainer = ResultData(
                    self._settings,
                    self._dssPath,
                    self._dssObjects,
                    self._dssObjectsByClass,
                    self._dssBuses,
                    self._dssSolver,
                    self._dssCommand,
                    self._dssInstance,
                )
            for is_complete, _, _, _ in self.run_simulation(project, scenario, i):
                if is_complete:
                    break
        return

    def _get_active_scenario(self):
        active_scenario = self._settings.project.active_scenario
        for scenario in self._settings.project.scenarios:
            if scenario.name == active_scenario:
                return scenario
        raise InvalidConfiguration(f"Active Scenario {active_scenario} is not present")

    @track_timing(timer_stats_collector)
    def _set_snapshot_time_point(self, scenario):
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
                logger.info(
                    "Changed simulation start time from %s to %s",
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


setattr(OpenDSS, "CreateBusObjects", OpenDSS.create_bus_objects)
setattr(OpenDSS, "CreateDssObjects", OpenDSS.create_dss_objects)
setattr(OpenDSS, "RunStep", OpenDSS.run_step)
setattr(OpenDSS, "RunSimulation", OpenDSS.run_simulation)
setattr(OpenDSS, "RunMCsimulation", OpenDSS.run_mc_simulation)
setattr(OpenDSS, "DryRunSimulation", OpenDSS.dry_run_simulation)
setattr(OpenDSS, "initStore", OpenDSS.init_store)
setattr(OpenDSS, "_RunPostProcessors", OpenDSS._run_post_processors)
setattr(OpenDSS, "_GetActiveScenario", OpenDSS._get_active_scenario)
setattr(OpenDSS, "_SetSnapshotTimePoint", OpenDSS._set_snapshot_time_point)
