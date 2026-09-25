from datetime import datetime
import pathlib
import os

import opendssdirect as dss
from loguru import logger
import pandas as pd

from pydss.unit_definitions import unit_info
from pydss.common import (
    PV_LOAD_SHAPE_FILENAME,
    PV_PROFILES_FILENAME,
    NODE_NAMES_BY_TYPE_FILENAME,
)
from pydss.dataset_buffer import DatasetBuffer
from pydss.utils.dss_utils import get_node_names_by_type
from pydss.exceptions import InvalidParameter
from pydss.export_list_reader import ExportListReader
from pydss.reports.reports import Reports, ReportGranularity
from pydss.simulation_input_models import SimulationSettingsModel
from pydss.utils.dataframe_utils import write_dataframe
from pydss.utils.utils import dump_data
from pydss.utils.simulation_utils import (
    create_datetime_index_from_settings,
    create_loadshape_pmult_dataframe_for_simulation,
)
from pydss.utils.timing_utils import Timer, timer_stats_collector, track_timing
from pydss.metrics import (
    OpenDssPropertyMetric,
    SummedElementsByGroupOpenDssPropertyMetric,
    SummedElementsOpenDssPropertyMetric,
)


class ResultData:
    """Exports data to files."""

    METADATA_FILENAME = "metadata.json"
    INDICES_BASENAME = "indices"

    def __init__(
        self,
        settings: SimulationSettingsModel,
        system_paths,
        dss_objects,
        dss_objects_by_class,
        dss_buses,
        dss_solver,
        dss_command,
        dss_instance,
    ):
        self._dss_solver = dss_solver
        self._results = {}
        self._buses = dss_buses
        self._objects_by_element = dss_objects
        self._objects_by_class = dss_objects_by_class
        self.system_paths = system_paths
        self._element_metrics = {}  # (elem_class, prop_name) to OpenDssPropertyMetric
        self._summed_element_metrics = {}
        self._settings = settings
        self._cur_step = 0
        self._current_results = {}

        self._dss_command = dss_command
        self._start_day = dss_solver.start_day
        self._end_day = dss_solver.end_day
        self._time_dataset = None
        self._frequency_dataset = None
        self._mode_dataset = None
        self._simulation_mode = []
        self._hdf_store = None
        self._scenario = settings.project.active_scenario
        self._base_scenario = settings.project.active_scenario
        self._export_format = settings.exports.export_format
        self._export_compression = settings.exports.export_compression
        self._max_chunk_bytes = settings.exports.hdf_max_chunk_bytes
        self._export_dir = os.path.join(
            self.system_paths["Export"],
            settings.project.active_scenario,
        )
        # Use / because this is used in HDFStore
        self._export_relative_dir = "Exports/" + settings.project.active_scenario
        self._store_frequency = False
        self._store_mode = False
        if settings.frequency.enable_frequency_sweep:
            self._store_frequency = True
            self._store_mode = True

        pathlib.Path(self._export_dir).mkdir(parents=True, exist_ok=True)

        export_list_filename = os.path.join(
            system_paths["ExportLists"],
            "Exports.toml",
        )
        if not os.path.exists(export_list_filename):
            export_list_filename = os.path.join(
                system_paths["ExportLists"],
                "ExportMode-byClass.toml",
            )
        self._export_list = ExportListReader(export_list_filename)
        Reports.append_required_exports(self._export_list, settings)
        dump_data(
            self._export_list.serialize(),
            os.path.join(self._export_dir, "ExportsActual.toml"),
        )
        self._circuit_metrics = {}
        self._create_exports()

    def _create_exports(self):
        for elem_class in self._export_list.list_element_classes():
            if elem_class in ("Buses", "Nodes"):
                objs = self._buses
            elif elem_class in self._objects_by_class:
                objs = self._objects_by_class[elem_class]
            elif elem_class == "FeederHead":
                objs = self._objects_by_class["Circuits"]
            elif elem_class != "CktElement":  # TODO
                continue
            for prop in self._export_list.iter_export_properties(elem_class=elem_class):
                if prop.opendss_classes:
                    dss_objs = []
                    for cls in prop.opendss_classes:
                        if cls not in self._objects_by_class:
                            logger.warning("Export class=%s is not present in the circuit", cls)
                            continue

                        for obj in self._objects_by_class[cls].values():
                            if obj.Enabled and prop.should_store_name(obj.FullName):
                                dss_objs.append(obj)
                else:
                    dss_objs = [
                        x for x in objs.values() if x.Enabled and prop.should_store_name(x.FullName)
                    ]
                if prop.custom_metric is None:
                    self._add_opendss_metric(prop, dss_objs)
                else:
                    self._add_custom_metric(prop, dss_objs)

    def _add_opendss_metric(self, prop, dss_objs):
        obj = dss_objs[0]
        if not obj.is_valid_attribute(prop.name):
            raise InvalidParameter(f"{obj.FullName} / {prop.name} cannot be exported")
        key = (prop.elem_class, prop.name)
        if prop.sum_elements:
            metric = self._summed_element_metrics.get(key)
            if metric is None:
                if prop.sum_groups:
                    cls = SummedElementsByGroupOpenDssPropertyMetric
                else:
                    cls = SummedElementsOpenDssPropertyMetric
                metric = cls(prop, dss_objs, self._settings)
                self._summed_element_metrics[key] = metric
            else:
                metric.add_dss_obj(obj)
        else:
            metric = self._element_metrics.get(key)
            if metric is None:
                metric = OpenDssPropertyMetric(prop, dss_objs, self._settings)
                self._element_metrics[key] = metric
            else:
                metric.add_property(prop)

    def _add_custom_metric(self, prop, dss_objs):
        cls = prop.custom_metric
        if cls.is_circuit_wide():
            metric = self._circuit_metrics.get(cls)
            if metric is None:
                metric = cls(prop, dss_objs, self._settings)
                self._circuit_metrics[cls] = metric
            else:
                metric.add_property(prop)
        else:
            key = (prop.elem_class, prop.name)
            metric = self._element_metrics.get(key)
            if metric is None:
                metric = cls(prop, dss_objs, self._settings)
                self._element_metrics[key] = metric
            else:
                metric.add_property(prop)

    def initialize_data_store(self, hdf_store, num_steps, mc_scenario_number=None):
        if mc_scenario_number is not None:
            self._scenario = self._base_scenario + f"_MC{mc_scenario_number}"
        self._hdf_store = hdf_store
        self._time_dataset = DatasetBuffer(
            hdf_store=hdf_store,
            path=f"Exports/{self._scenario}/Timestamp",
            max_size=num_steps,
            dtype=float,
            columns=("Timestamp",),
            max_chunk_bytes=self._max_chunk_bytes,
        )
        self._frequency_dataset = DatasetBuffer(
            hdf_store=hdf_store,
            path=f"Exports/{self._scenario}/Frequency",
            max_size=num_steps,
            dtype=float,
            columns=("Frequency",),
            max_chunk_bytes=self._max_chunk_bytes,
        )
        self._mode_dataset = DatasetBuffer(
            hdf_store=hdf_store,
            path=f"Exports/{self._scenario}/Mode",
            max_size=num_steps,
            dtype="S10",
            columns=("Mode",),
            max_chunk_bytes=self._max_chunk_bytes,
        )
        self._cur_step = 0

        base_path = "Exports/" + self._scenario
        for metric in self._iter_metrics():
            metric.initialize_data_store(hdf_store, base_path, num_steps)

    def _iter_metrics(self):
        for metric in self._element_metrics.values():
            yield metric
        for metric in self._summed_element_metrics.values():
            yield metric
        for metric in self._circuit_metrics.values():
            yield metric

    @property
    def current_results(self):
        return self._current_results

    @track_timing(timer_stats_collector)
    def update_results(self, store_nan=False):
        self._current_results.clear()

        # Get the number of seconds since the Epoch without any timezone conversions.
        timestamp = (
            self._dss_solver.GetDateTime() - datetime(1970, 1, 1, 0, 0)
        ).total_seconds()  #  datetime.utcfromtimestamp(0) is now depriciated
        self._time_dataset.write_value([timestamp])
        self._frequency_dataset.write_value([self._dss_solver.getFrequency()])
        self._mode_dataset.write_value([self._dss_solver.getMode()])

        for metric in self._iter_metrics():
            with Timer(timer_stats_collector, metric.label()):
                data = metric.append_values(self._cur_step, store_nan=store_nan)

            if isinstance(data, dict):
                # TODO: reconsider
                # Something is only returned for OpenDSS properties
                self._current_results.update(data)

        self._cur_step += 1
        return self._current_results

    def export_results(self):
        metadata = {
            "event_log": None,
            "element_info_files": [],
        }

        if self._settings.exports.export_event_log:
            self._export_event_log(metadata)
        if self._settings.exports.export_elements:
            self._export_elements(metadata, set(self._settings.exports.export_element_types))
            self._export_feeder_head_info(metadata)
        if self._settings.exports.export_pv_profiles:
            self._export_pv_profiles()
        if self._settings.exports.export_node_names_by_type:
            self._export_node_names_by_type()

        filename = os.path.join(self._export_dir, self.METADATA_FILENAME)
        dump_data(metadata, filename, indent=4)
        logger.info(
            f"Exported metadata to {filename}",
        )
        self._hdf_store = None

    def close(self):
        for dataset in (self._time_dataset, self._frequency_dataset, self._mode_dataset):
            dataset.flush_data()
        for metric in self._iter_metrics():
            metric.close()

    def _export_event_log(self, metadata):
        event_log = "event_log.csv"
        file_path = os.path.join(self._export_dir, event_log)
        if os.path.exists(file_path):
            os.remove(file_path)

        orig = os.getcwd()
        os.chdir(self._export_dir)
        try:
            cmd = "Export EventLog {}".format(event_log)
            out = self._dss_command(cmd)
            if out != event_log:
                raise Exception(f"Failed to export EventLog:  {out}")
            logger.info(
                f"Exported OpenDSS event log to {out}",
            )
            metadata["event_log"] = self._export_relative_dir + f"/{event_log}"
        finally:
            os.chdir(orig)

    def _export_dataframe(self, df, basename):
        filename = basename + "." + self._export_format
        write_dataframe(df, filename, compress=self._export_compression)
        logger.info("Exported %s", filename)

    def _find_feeder_head_line(self):
        feeder_head_line = None
        flag = dss.Topology.First()
        while flag > 0:
            if "line" in dss.Topology.BranchName().lower():
                feeder_head_line = dss.Topology.BranchName()
                break
            else:
                flag = dss.Topology.Next()

        return feeder_head_line

    def _get_feeder_head_loading(self):
        head_line = self._find_feeder_head_line()
        if head_line is not None:
            flag = dss.Circuit.SetActiveElement(head_line)

            if flag > 0:
                n_phases = dss.CktElement.NumPhases()
                max_amp = dss.CktElement.NormalAmps()
                currents = dss.CktElement.CurrentsMagAng()[: 2 * n_phases]
                current_magnitude = currents[::2]

                max_flow = max(max(current_magnitude), 1e-10)
                loading = max_flow / max_amp

                return loading
            else:
                return None
        else:
            return None

    def _reverse_powerflow(self):
        reverse_pf = (
            dss.Circuit.TotalPower()[0] > 0
        )  # total substation power is an injection(-) or a consumption(+)
        return reverse_pf

    def _export_feeder_head_info(self, metadata):
        """
        Gets feeder head information comprising:
        1- The name of the feeder head line
        2- The feeder head loading in per unit
        3- The feeder head load in (kW, kVar). Negative in case of power injection
        4- The reverse power flow flag. True if power is flowing back to the feeder head, False otherwise
        """
        if "feeder_head_info_files" not in metadata.keys():
            metadata["feeder_head_info_files"] = []

        total_power = dss.Circuit.TotalPower()
        df_dict = {
            "FeederHeadLine": self._find_feeder_head_line(),
            "FeederHeadLoading": self._get_feeder_head_loading(),
            "FeederHeadLoadKW": total_power[0],
            "FeederHeadLoadKVar": total_power[1],
            "ReversePowerFlow": self._reverse_powerflow(),
        }

        filename = "FeederHeadInfo"
        fname = filename + ".json"
        relpath = os.path.join(self._export_relative_dir, fname)
        filepath = os.path.join(self._export_dir, fname)

        # write_dataframe(df, filepath)
        dump_data(df_dict, filepath)
        metadata["feeder_head_info_files"].append(relpath)
        logger.info("Exported %s information to %s.", filename, filepath)

    def _export_elements(self, metadata, element_types):
        exports = [
            # TODO: opendssdirect does not provide a function to export Bus information.
            ("Capacitor", "CapacitorsInfo", dss.Capacitors.Count),
            ("Fuse", "FusesInfo", dss.Fuses.Count),
            ("Generator", "GeneratorsInfo", dss.Generators.Count),
            ("Isource", "IsourceInfo", dss.Isource.Count),
            ("Line", "LinesInfo", dss.Lines.Count),
            ("Load", "LoadsInfo", dss.Loads.Count),
            ("Monitor", "MonitorsInfo", dss.Monitors.Count),
            ("PVSystem", "PVSystemsInfo", dss.PVsystems.Count),
            ("Recloser", "ReclosersInfo", dss.Reclosers.Count),
            ("RegControl", "RegControlsInfo", dss.RegControls.Count),
            ("Relay", "RelaysInfo", dss.Relays.Count),
            ("Sensor", "SensorsInfo", dss.Sensors.Count),
            ("Transformer", "TransformersInfo", dss.Transformers.Count),
            ("Vsource", "VsourcesInfo", dss.Vsources.Count),
            ("XYCurve", "XYCurvesInfo", dss.XYCurves.Count),
            # TODO This can be very large. Consider making it configurable.
            # ("LoadShape", "LoadShapeInfo", dss.LoadShape.Count),
        ]
        if element_types:
            types = set()
            for elem_type in element_types:
                if elem_type.endswith("s"):
                    # Maintain compatibility with old format used plural names.
                    elem_type = elem_type[:-1]
                types.add(elem_type)
            exports = [x for x in exports if x[0] in types]

        for class_name, filename, count_func in exports:
            df = dss.utils.class_to_dataframe(class_name)
            # Always record in CSV format for readability.
            # There are also warning messages from PyTables because the
            # data may contain strings.
            fname = filename + ".csv"
            relpath = os.path.join(self._export_relative_dir, fname)
            filepath = os.path.join(self._export_dir, fname)
            write_dataframe(df, filepath)
            metadata["element_info_files"].append(relpath)
            logger.info("Exported %s information to %s.", filename, filepath)

        if not element_types or "Transformer" in element_types or "Transformers" in element_types:
            self._export_transformers(metadata)

    def _export_transformers(self, metadata):
        df_dict = {"Transformer": [], "HighSideConnection": [], "NumPhases": []}

        dss.Circuit.SetActiveClass("Transformer")
        flag = dss.ActiveClass.First()
        while flag > 0:
            name = dss.CktElement.Name()
            df_dict["Transformer"].append(name)
            df_dict["HighSideConnection"].append(
                dss.Properties.Value("conns").split("[")[1].split(",")[0].strip(" ").lower()
            )
            df_dict["NumPhases"].append(dss.CktElement.NumPhases())
            flag = dss.ActiveClass.Next()

        df = pd.DataFrame.from_dict(df_dict)

        relpath = os.path.join(self._export_relative_dir, "TransformersPhaseInfo.csv")
        filepath = os.path.join(self._export_dir, "TransformersPhaseInfo.csv")
        write_dataframe(df, filepath)
        metadata["element_info_files"].append(relpath)
        logger.info("Exported transformer phase information to %s", filepath)

    def _export_pv_profiles(self):
        granularity = self._settings.reports.granularity
        pv_systems = self._objects_by_class.get("PVSystems")
        if pv_systems is None:
            logger.info("No PVSystems are present")
            return

        pv_infos = []
        profiles = set()
        for full_name, obj in pv_systems.items():
            profile_name = obj.GetParameter("yearly").lower()
            if profile_name != "":
                profiles.add(profile_name)
            pv_infos.append(
                {
                    "irradiance": obj.GetParameter("irradiance"),
                    "name": full_name,
                    "pmpp": obj.GetParameter("pmpp"),
                    "load_shape_profile": profile_name,
                }
            )

        pmult_sums = {}
        if dss.LoadShape.First() == 0:
            logger.warning("There are no load shapes.")
            return

        sim_resolution = self._settings.project.step_resolution_sec
        per_time_point = (
            ReportGranularity.PER_ELEMENT_PER_TIME_POINT,
            ReportGranularity.ALL_ELEMENTS_PER_TIME_POINT,
        )
        load_shape_data = {}
        while True:
            name = dss.LoadShape.Name().lower()
            if name in profiles:
                sinterval = dss.LoadShape.SInterval()
                assert sim_resolution >= sinterval, f"{sim_resolution} >= {sinterval}"
                df = create_loadshape_pmult_dataframe_for_simulation(self._settings)
                sum_values = df.iloc[:, 0].sum()
                if granularity in per_time_point:
                    load_shape_data[name] = df.iloc[:, 0].values
                    pmult_sums[name] = sum_values
                else:
                    pmult_sums[name] = sum_values
            if dss.LoadShape.Next() == 0:
                break

        if load_shape_data and granularity in per_time_point:
            filename = os.path.join(self._export_dir, PV_LOAD_SHAPE_FILENAME)
            index = create_datetime_index_from_settings(self._settings)
            df = pd.DataFrame(load_shape_data, index=index)
            write_dataframe(df, filename, compress=True)

        for pv_info in pv_infos:
            profile = pv_info["load_shape_profile"]
            if profile == "":
                pv_info["load_shape_pmult_sum"] = 0
            else:
                pv_info["load_shape_pmult_sum"] = pmult_sums[profile]

        data = {"pv_systems": pv_infos}
        filename = os.path.join(self._export_dir, PV_PROFILES_FILENAME)
        dump_data(data, filename, indent=2)
        logger.info("Exported PV profile information to %s", filename)

    def _export_node_names_by_type(self):
        data = get_node_names_by_type()
        filename = os.path.join(self._export_dir, NODE_NAMES_BY_TYPE_FILENAME)
        dump_data(data, filename, indent=2)
        logger.info("Exported node names by type to %s", filename)

    @staticmethod
    def get_units(prop, index=None):
        units = unit_info.get(prop)
        if units is None:
            raise InvalidParameter(f"no units are stored for {prop}")

        if isinstance(units, dict):
            if index is None:
                raise InvalidParameter(f"index must be provided for {prop}")
            if index == 0:
                return units["E"]
            if index == 1:
                return units["O"]
            raise InvalidParameter("index must be 0 or 1")

        return units

    def max_num_bytes(self):
        """Return the maximum number of bytes the container could hold.

        Returns
        -------
        int

        """
        total = 0
        for metric in self._iter_metrics():
            total += metric.max_num_bytes()
        return total


ResultData.InitializeDataStore = ResultData.initialize_data_store
ResultData.CurrentResults = property(lambda self: self.current_results)
ResultData.UpdateResults = ResultData.update_results
ResultData.ExportResults = ResultData.export_results
ResultData.Close = ResultData.close
