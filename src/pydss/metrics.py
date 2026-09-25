import abc
import copy
import os
import shutil
import tempfile
from collections import namedtuple
from datetime import timedelta
from pathlib import Path

from loguru import logger
import pandas as pd
import opendssdirect as dss

from pydss.common import DataConversion, StoreValuesType
from pydss.exceptions import InvalidConfiguration, InvalidParameter
from pydss.reports.reports import ReportBase
from pydss.storage_filters import STORAGE_TYPE_MAP, StorageFilterBase
from pydss.value_storage import ValueByNumber, ValueStorageBase
from pydss.node_voltage_metrics import NodeVoltageMetrics
from pydss.simulation_input_models import SimulationSettingsModel
from pydss.thermal_metrics import ThermalMetrics
from pydss.utils.simulation_utils import get_start_time, get_simulation_resolution


class MetricBase(abc.ABC):
    """Base class for all metrics"""

    def __init__(self, prop, dss_objs, settings: SimulationSettingsModel):
        self._name = prop.name
        self._base_path = None
        self._hdf_store = None
        self._max_chunk_bytes = settings.exports.hdf_max_chunk_bytes
        self._num_steps = None
        self._properties = {}  # StoreValuesType to ExportListProperty
        self._dss_objs = dss_objs
        self._name_to_dss_obj = {x.Name: x for x in dss_objs}
        self._elem_class = _OPEN_DSS_CLASS_FOR_ITERATION.get(dss_objs[0]._Class)
        self._settings = settings
        self._are_names_filtered = prop.are_names_filtered

        self.add_property(prop)

    def add_property(self, prop):
        """Add an instance of ExportListProperty for tracking."""
        if prop.are_names_filtered != self._are_names_filtered:
            raise InvalidConfiguration(
                f"All properties for shared elements must have the same filters: "
                f"{self._elem_class.__name__} / {prop.name}."
            )
        existing = self._properties.get(prop.store_values_type)
        if existing is None:
            self._properties[prop.store_values_type] = prop
        elif prop != existing:
            raise InvalidParameter(f"{prop.store_values_type} is already stored")

    @abc.abstractmethod
    def append_values(self, time_step, store_nan=False):
        """Get the values for all elements at the current time step."""

    def close(self):
        """Perform any final writes to the container."""
        for container in self.iter_containers():
            if container is not None:
                container.close()

        # Write an empty dataset to the .h5 file if no data was collected.
        for prop in self.iter_empty_containers():
            assert not isinstance(self, SummedElementsOpenDssPropertyMetric)
            path = f"{self._base_path}/{prop.elem_class}/ElementProperties/{prop.storage_name}"
            self.make_empty_storage_container(path, prop)

    def flush_data(self):
        """Flush any data in memory to storage."""
        for container in self.iter_containers():
            container.flush_data()

    def initialize_data_store(self, hdf_store, base_path, num_steps):
        """Initialize data store values."""
        self._hdf_store = hdf_store
        self._base_path = base_path
        self._num_steps = num_steps

    @staticmethod
    def is_circuit_wide():
        """Return True if this metric should be used once for a circuit."""
        return False

    @abc.abstractmethod
    def iter_containers(self):
        """Return an iterator over the StorageFilterBase containers."""

    def iter_empty_containers(self):
        """Return an iterator over empty containers."""
        return
        yield

    def label(self):
        """Return a label for the metric.

        Returns
        -------
        str

        """
        prop = next(iter(self._properties.values()))
        return f"{prop.elem_class}.{prop.name}"

    def _make_elem_names(self):
        return [x.FullName for x in self._dss_objs]

    def make_empty_storage_container(self, path, prop):
        """Make an empty storage container."""
        if prop.store_values_type not in STORAGE_TYPE_MAP:
            raise InvalidConfiguration(f"unsupported {prop.store_values_type}")
        elem_names = self._make_elem_names()
        cls = STORAGE_TYPE_MAP[prop.store_values_type]
        values = [ValueByNumber(x.FullName, self.label(), 0.0) for x in self._dss_objs]
        container = cls(self._hdf_store, path, prop, 1, self._max_chunk_bytes, values, elem_names)
        return container

    def make_storage_container(self, path, prop, num_steps, max_chunk_bytes, values, **kwargs):
        """Make a storage container.

        Returns
        -------
        StorageFilterBase

        """
        if prop.store_values_type not in STORAGE_TYPE_MAP:
            raise InvalidConfiguration(f"unsupported {prop.store_values_type}")
        elem_names = self._make_elem_names()
        cls = STORAGE_TYPE_MAP[prop.store_values_type]
        container = cls(
            self._hdf_store,
            path,
            prop,
            num_steps,
            max_chunk_bytes,
            values,
            elem_names,
            **kwargs,
        )
        return container

    def max_num_bytes(self):
        """Return the maximum number of bytes the containers could hold.

        Returns
        -------
        int

        """
        total = 0
        for container in self.iter_containers():
            if container is not None:
                total += container.max_num_bytes()
        return total

    def _can_use_native_iteration(self):
        return self._elem_class is not None and not self._are_names_filtered


class ChangeCountMetricBase(MetricBase, abc.ABC):
    """Base class for any metric that only tracks number of changes."""

    def __init__(self, prop, dss_objs, settings: SimulationSettingsModel):
        super().__init__(prop, dss_objs, settings)
        self._container = None
        self._last_values = {x.FullName: None for x in dss_objs}
        self._change_counts = {x.FullName: 0 for x in dss_objs}

    def append_values(self, time_step, store_nan=False):
        pass

    def close(self):
        assert len(self._properties) == 1
        prop = next(iter(self._properties.values()))
        path = f"{self._base_path}/{prop.elem_class}/ElementProperties/{prop.storage_name}"
        values = [ValueByNumber(x, prop.name, y) for x, y in self._change_counts.items()]
        # This class creates an instance of ValueContainer directly because
        # these metrics can only store one type, and so don't need an instance
        # of StorageFilterBase.
        self._container = StorageFilterBase.make_container(
            self._hdf_store,
            path,
            prop,
            self._num_steps,
            self._max_chunk_bytes,
            values,
            [x.FullName for x in self._dss_objs],
        )
        self._container.append(values)
        self._container.flush_data()

    def iter_containers(self):
        yield self._container


class MultiValueTypeMetricBase(MetricBase, abc.ABC):
    """Stores a property with multiple values of StoreValueType.

    For example, a user might want to store a moving average as well as the
    max of all instantaneous values.

    """

    def __init__(self, prop, dss_objs, settings):
        super().__init__(prop, dss_objs, settings)
        self._containers = {}  # StoreValuesType to StorageFilterBase
        self._name_order = []  # Ensures that name-value ordering will always be consistent.

    def _iter_dss_objs(self):
        if self._can_use_native_iteration():
            flag = self._elem_class.First()
            while flag > 0:
                name = self._elem_class.Name()
                dss_obj = self._name_to_dss_obj[name]
                yield dss_obj
                flag = self._elem_class.Next()
        else:
            yield from self._dss_objs

    @abc.abstractmethod
    def _get_value(self, dss_obj, time_step):
        """Get a value at the current time step.

        Parameters
        ----------
        dss_obj : dssObjBase
        time_step : int

        """

    def _initialize_containers(self, values):
        prop_name = None
        for prop in self._properties.values():
            if prop_name is None:
                prop_name = prop.name
            else:
                assert prop.name == prop_name, f"{prop.name} {prop_name}"
            if prop.data_conversion != DataConversion.NONE:
                vals = [
                    convert_data(x, prop_name, y, prop.data_conversion)
                    for x, y in zip(self._name_order, values)
                ]
            else:
                vals = values
            path = f"{self._base_path}/{prop.elem_class}/ElementProperties/{prop.storage_name}"
            self._containers[prop.store_values_type] = self.make_storage_container(
                path,
                prop,
                self._num_steps,
                self._max_chunk_bytes,
                vals,
            )

    def append_values(self, time_step, store_nan=False):
        if not self._name_order:
            self._name_order[:] = [x.FullName for x in self._iter_dss_objs()]

        # values = [self._get_value(x, time_step) for x in self._dss_objs]
        values = []
        objects_changed = False
        for dss_obj, expected_name in zip(self._iter_dss_objs(), self._name_order):
            if dss_obj.FullName != expected_name:
                # This can happen if an element is disabled. OpenDSS won't deliver it in .Next()
                # Need to access the element directly, which breaks the iteration.
                objects_changed = True
                break
            values.append(self._get_value(dss_obj, time_step))

        if objects_changed or not values:
            values = [self._get_value(x, time_step) for x in self._dss_objs]

        assert len(values) == len(self._dss_objs)

        if not self._containers:
            self._initialize_containers(values)

        if store_nan:
            for val in values:
                val.set_nan()

        for value_type, container in self._containers.items():
            prop = self._properties[value_type]
            if prop.data_conversion != DataConversion.NONE:
                assert len(self._name_order) == len(values)
                vals = [
                    convert_data(x, prop.name, y, prop.data_conversion)
                    for x, y in zip(self._name_order, values)
                ]
            else:
                vals = values
            container.append_values(vals, time_step)

        return vals

    def iter_containers(self):
        return self._containers.values()

    def iter_empty_containers(self):
        for prop in self._properties.values():
            if prop.store_values_type not in self._containers:
                yield prop


class OpenDssPropertyMetric(MultiValueTypeMetricBase):
    """Stores metrics for any OpenDSS element property."""

    def _get_value(self, dss_obj, _time_step):
        return dss_obj.update_value(self._name)

    def append_values(self, time_step, store_nan=False):
        curr_data = {}
        values = super().append_values(time_step, store_nan=store_nan)
        for _, value in zip(self._dss_objs, values):
            if len(value.make_columns()) > 1:
                for column, val in zip(value.make_columns(), value.value):
                    curr_data[column] = val
            else:
                curr_data[value.make_columns()[0]] = value.value

        return curr_data


# These next two might work but are untested.

# class LineLoadingPercent(MultiValueTypeMetricBase):
#    """Calculates line loading percent at every time point."""
#
#    def __init__(self, prop, dss_objs, settings):
#        super().__init__(prop, dss_objs, settings)
#        self._normal_amps = {}  # Name to normal_amps value
#
#    def _get_value(self, dss_obj, _time_step):
#        line = dss_obj
#        normal_amps = self._normal_amps.get(line.Name)
#        if normal_amps is None:
#            normal_amps = line.get_value("NormalAmps", convert=True).value
#            self._normal_amps[line.Name] = normal_amps
#
#        currents = line.update_value("Currents").value
#        current = max([abs(x) for x in currents])
#        loading = current / normal_amps * 100
#        return ValueByNumber(line.Name, "LineLoading", loading)
#
#
# class TransformerLoadingPercent(MultiValueTypeMetricBase):
#    """Calculates transformer loading percent at every time point."""
#
#    def __init__(self, prop, dss_objs, settings):
#        super().__init__(prop, dss_objs, settings)
#        self._normal_amps = {}  # Name to normal_amps value
#
#    def _get_value(self, dss_obj, _time_step):
#        transformer = dss_obj
#        normal_amps = self._normal_amps.get(transformer.Name)
#        if normal_amps is None:
#            normal_amps = transformer.get_value("NormalAmps", convert=True).value
#            self._normal_amps[transformer.Name] = normal_amps
#
#        currents = transformer.update_value("Currents").value
#        current = max([abs(x) for x in currents])
#        loading = current / normal_amps * 100
#        return ValueByNumber(transformer.Name, "TransformerLoading", loading)


FeederHeadValues = namedtuple(
    "FeederHeadValues", ["load_kvar", "load_kw", "loading", "reverse_power_flow"]
)


class FeederHeadMetrics(MetricBase):
    """Calculates loading at the feeder head at each time point"""

    def __init__(self, prop, dss_objs, settings):
        super().__init__(prop, dss_objs, settings)
        # dss_objs contains the Circuit, but we won't use it.
        assert len(dss_objs) == 1, dss_objs
        self._prop = prop
        self._containers = {}
        self._feeder_head_line = None
        self._values = {}

    def _initialize_containers(self):
        assert len(self._properties) == 1, self._properties
        self._feeder_head_line = self._find_feeder_head_line()
        values = self._get_values()
        self._values = {
            "load_kvar": ValueByNumber("FeederHead", "load_kvar", values.load_kvar),
            "load_kw": ValueByNumber("FeederHead", "load_kw", values.load_kw),
            "loading": ValueByNumber("FeederHead", "loading", values.loading),
            "reverse_power_flow": ValueByNumber(
                "FeederHead", "reverse_power_flow", values.reverse_power_flow
            ),
        }

        for name in self._values:
            path = f"{self._base_path}/{self._prop.elem_class}/ElementProperties/{name}"
            self._containers[name] = self.make_storage_container(
                path,
                self._prop,
                self._num_steps,
                self._max_chunk_bytes,
                [self._values[name]],
            )

    @staticmethod
    def is_circuit_wide():
        return True

    @staticmethod
    def _find_feeder_head_line():
        feeder_head_line = None
        flag = dss.Topology.First()
        while flag > 0:
            if "line" in dss.Topology.BranchName().lower():
                feeder_head_line = dss.Topology.BranchName()
                break
            flag = dss.Topology.Next()

        assert feeder_head_line is not None
        return feeder_head_line

    def _get_values(self):
        total_power = dss.Circuit.TotalPower()
        feeder_head_values = FeederHeadValues(
            load_kvar=total_power[1],
            load_kw=total_power[0],
            loading=self._get_feeder_head_loading(),
            reverse_power_flow=self._reverse_power_flow(),
        )
        return feeder_head_values

    def _get_feeder_head_loading(self):
        flag = dss.Circuit.SetActiveElement(self._feeder_head_line)
        if not flag > 0:
            raise Exception("Failed to set the feeder head line")
        n_phases = dss.CktElement.NumPhases()
        max_amps = dss.CktElement.NormalAmps()
        currents = dss.CktElement.CurrentsMagAng()[: 2 * n_phases]
        current_magnitude = currents[::2]

        max_flow = max(max(current_magnitude), 1e-10)
        loading = max_flow / max_amps
        return loading

    @staticmethod
    def _reverse_power_flow():
        # total substation power is an injection(-) or a consumption(+)
        reverse_pf = dss.Circuit.TotalPower()[0] > 0
        # Storing NaN with bools is not working correctly.
        return int(reverse_pf)

    def append_values(self, time_step, store_nan=False):
        if not self._containers:
            self._initialize_containers()

        if store_nan:
            for val in self._values.values():
                val.set_nan()
        else:
            values = self._get_values()
            for name, value in self._values.items():
                value.set_value(getattr(values, name))

        vals = []
        for name, container in self._containers.items():
            value = self._values[name]
            vals.append(value)
            container.append_values([value], time_step)

        return vals

    def iter_containers(self):
        for container in self._containers.values():
            yield container


class SummedElementsOpenDssPropertyMetric(MetricBase):
    """Sums all elements' values for a given property at each time point."""

    def __init__(self, prop, dss_objs, settings):
        super().__init__(prop, dss_objs, settings)
        self._container = None
        self._data_conversion = prop.data_conversion

    def _get_value(self, obj):
        value = obj.update_value(self._name)
        if self._data_conversion != DataConversion.NONE:
            value = convert_data(
                "Total",
                next(iter(self._properties.values())).name,
                value,
                self._data_conversion,
            )
        return value

    def append_values(self, time_step, store_nan=False):
        if store_nan:
            if self._can_use_native_iteration():
                self._elem_class.First()
            total = self._get_value(self._dss_objs[0])
            total.set_nan()
        else:
            total = None
            if self._can_use_native_iteration():
                iterations = 0
                flag = self._elem_class.First()
                while flag > 0:
                    dss_obj = self._name_to_dss_obj[self._elem_class.Name()]
                    value = self._get_value(dss_obj)
                    if total is None:
                        total = value
                    else:
                        total += value
                    iterations += 1
                    flag = self._elem_class.Next()
                assert iterations == len(self._dss_objs)
            else:
                for dss_obj in self._dss_objs:
                    value = self._get_value(dss_obj)
                    if total is None:
                        total = value
                    else:
                        total += value

        if self._container is None:
            assert len(self._properties) == 1
            prop = next(iter(self._properties.values()))
            assert prop.store_values_type in (StoreValuesType.ALL, StoreValuesType.SUM)
            total.set_name("Total")
            path = (
                f"{self._base_path}/{prop.elem_class}/SummedElementProperties/{prop.storage_name}"
            )
            self._container = self.make_storage_container(
                path,
                prop,
                self._num_steps,
                self._max_chunk_bytes,
                [total],
            )
        self._container.append_values([total], time_step)

    @staticmethod
    def is_circuit_wide():
        return True

    def iter_containers(self):
        yield self._container


class SummedElementsByGroupOpenDssPropertyMetric(MetricBase):
    """Sums all elements' values for a given property at each time point.
    Elements are separated into groups by name.

    """

    def __init__(self, prop, dss_objs, settings):
        super().__init__(prop, dss_objs, settings)
        self._containers = {}
        self._name_to_group = {}

        # This allows names to be in the group that aren't in the circuit
        # in order to reduce having to duplicate the sum_group files many times
        # in cases where there are many projects/scenarios.
        elements = {x.Name for x in dss_objs}
        for group in prop.sum_groups:
            group_elems = elements.intersection(set(group["elements"]))
            if group_elems:
                self._containers[group["name"]] = None
                for element_name in group_elems:
                    self._name_to_group[element_name] = group["name"]

        self._data_conversion = prop.data_conversion

    def _get_value(self, obj):
        value = obj.update_value(self._name)
        if self._data_conversion != DataConversion.NONE:
            value = convert_data(
                "Total",
                next(iter(self._properties.values())).name,
                value,
                self._data_conversion,
            )
        return value

    def append_values(self, time_step, store_nan=False):
        total_by_group = {x: None for x in self._containers}
        if store_nan:
            for group in self._containers:
                if self._can_use_native_iteration():
                    self._elem_class.First()
                total_by_group[group] = self._get_value(self._dss_objs[0])
                total_by_group[group].set_nan()
        else:
            if self._can_use_native_iteration():
                iterations = 0
                flag = self._elem_class.First()
                while flag > 0:
                    name = self._elem_class.Name()
                    group = self._name_to_group[name]
                    dss_obj = self._name_to_dss_obj[name]
                    value = self._get_value(dss_obj)
                    if total_by_group[group] is None:
                        total_by_group[group] = value
                    else:
                        total_by_group[group] += value
                    iterations += 1
                    flag = self._elem_class.Next()
                assert iterations == len(self._dss_objs)
            else:
                for dss_obj in self._dss_objs:
                    value = self._get_value(dss_obj)
                    if total_by_group[group] is None:
                        total_by_group[group] = value
                    else:
                        total_by_group[group] += value

        if next(iter(self._containers.values())) is None:
            assert len(self._properties) == 1
            prop = next(iter(self._properties.values()))
            assert prop.store_values_type in (StoreValuesType.ALL, StoreValuesType.SUM)
            for group in self._containers:
                total_by_group[group].set_name("Total")
                key = ValueStorageBase.DELIMITER.join((prop.storage_name, group))
                path = f"{self._base_path}/{prop.elem_class}/SummedElementProperties/{key}"
                self._containers[group] = self.make_storage_container(
                    path,
                    prop,
                    self._num_steps,
                    self._max_chunk_bytes,
                    [total_by_group[group]],
                )
        for group in self._containers:
            self._containers[group].append_values([total_by_group[group]], time_step)

    @staticmethod
    def is_circuit_wide():
        return True

    def iter_containers(self):
        return self._containers.values()


class NodeVoltageMetric(MetricBase):
    """Stores metrics for node voltages."""

    PRIMARY_BUS_THRESHOLD_KV = 1.0

    def __init__(self, prop, dss_obj, settings):
        super().__init__(prop, dss_obj, settings)
        props = list(self._properties)
        assert len(props) == 1
        self._prop = props[0]
        # Indices for node names are tied to indices for node voltages.
        self._node_names = None
        self._voltages = None
        start_time = get_start_time(settings)
        sim_resolution = get_simulation_resolution(settings)
        inputs = ReportBase.get_inputs_from_defaults(settings, "Voltage Metrics")
        window_size = max(1, int(timedelta(minutes=inputs["window_size_minutes"]) / sim_resolution))
        self._voltage_metrics = NodeVoltageMetrics(
            prop, start_time, sim_resolution, window_size, inputs["store_per_element_data"]
        )
        self._primary_node_names = []
        self._primary_indices = []
        self._secondary_node_names = []
        self._secondary_indices = []

    def _make_elem_names(self):
        return self._node_names

    def _identify_primary_v_secondary(self):
        for i, name in enumerate(self._node_names):
            dss.Circuit.SetActiveBus(name)
            kv_base = dss.Bus.kVBase()
            if kv_base > self.PRIMARY_BUS_THRESHOLD_KV:
                self._primary_node_names.append(name)
                self._primary_indices.append(i)
            else:
                self._secondary_node_names.append(name)
                self._secondary_indices.append(i)

    def append_values(self, time_step, store_nan=False):
        voltages = dss.Circuit.AllBusMagPu()
        if self._voltages is None:
            # TODO: limit to objects that have been added
            self._node_names = dss.Circuit.AllNodeNames()
            self._identify_primary_v_secondary()
            self._voltages = [
                ValueByNumber(x, "Voltage", y) for x, y in zip(self._node_names, voltages)
            ]
            self._voltage_metrics.set_node_info(
                self._primary_node_names,
                self._primary_indices,
                self._secondary_node_names,
                self._secondary_indices,
            )
        else:
            for i, voltage in enumerate(voltages):
                self._voltages[i].set_value_from_raw(voltage)

        if not store_nan:
            self._voltage_metrics.update(time_step, self._voltages)

        self._voltage_metrics.increment_steps()

    def close(self):
        path = os.path.join(
            str(self._settings.project.active_project_path),
            "Exports",
            self._settings.project.active_scenario,
        )
        self._voltage_metrics.generate_report(path)

    @staticmethod
    def is_circuit_wide():
        return True

    def iter_containers(self):
        return
        yield


class TrackCapacitorChangeCounts(ChangeCountMetricBase):
    """Store the number of changes for a capacitor."""

    def append_values(self, _time_step, store_nan=False):
        if store_nan:
            return

        iterations = 0
        flag = dss.Capacitors.First()
        while flag > 0:
            capacitor = self._name_to_dss_obj[dss.Capacitors.Name()]
            self._update_counts(capacitor)
            iterations += 1
            flag = dss.Capacitors.Next()
        assert iterations == len(self._dss_objs)

    def _update_counts(self, capacitor):
        states = dss.Capacitors.States()
        if states == -1:
            raise Exception(f"failed to get Capacitors.States() for {capacitor.Name}")

        if len(states) != 1:
            raise Exception(f"length of states greater than 1 is not supported: {states}")
        cur_value = sum(states)
        last_value = self._last_values[capacitor.FullName]
        if last_value is not None and cur_value != last_value:
            logger.debug("%s changed state old=%s new=%s", capacitor.Name, last_value, cur_value)
            self._change_counts[capacitor.FullName] += 1

        self._last_values[capacitor.FullName] = cur_value


class TrackRegControlTapNumberChanges(ChangeCountMetricBase):
    """Store the number of tap number changes for a RegControl."""

    def append_values(self, _time_step, store_nan=False):
        if store_nan:
            return

        iterations = 0
        flag = dss.RegControls.First()
        while flag > 0:
            reg_control = self._name_to_dss_obj[dss.RegControls.Name()]
            self._update_counts(reg_control)
            iterations += 1
            flag = dss.RegControls.Next()
        assert iterations == len(self._dss_objs)

    def _update_counts(self, reg_control):
        tap_number = dss.RegControls.TapNumber()
        last_value = self._last_values[reg_control.FullName]
        if last_value is not None and last_value != tap_number:
            self._change_counts[reg_control.FullName] += 1
            logger.debug(
                "%s changed count from %s to %s count=%s",
                reg_control.Name,
                last_value,
                tap_number,
                self._change_counts[reg_control.FullName],
            )

        self._last_values[reg_control.FullName] = tap_number


class OpenDssExportMetric(MetricBase):
    def __init__(self, prop, dss_objs, settings):
        super().__init__(prop, dss_objs, settings)
        self._tmp_dir = tempfile.mkdtemp()
        self._containers = {}
        self._sum_elements = prop.sum_elements
        if self._sum_elements:
            self._append_func = self._append_summed_values
        else:
            self._append_func = self._append_values
        self._check_output()

        # Some OpenDSS files upper-case the name.
        # Make a mapping for fast matching and lookup.
        self._names = {}
        self._values = []
        for i, dss_obj in enumerate(dss_objs):
            elem_type, name = dss_obj.FullName.split(".")
            if self.requires_upper_case():
                self._names[f"{elem_type}.{name.upper()}"] = i
            else:
                self._names[f"{elem_type}.{name}"] = i
            if self._sum_elements and not self._values:
                self._values.append(ValueByNumber("Total", self.label(), 0.0))
                break
            self._values.append(ValueByNumber(dss_obj.FullName, self.label(), 0.0))

    def __del__(self):
        shutil.rmtree(self._tmp_dir)

    def _run_command(self):
        cmd = f"{self.export_command()}"
        result = dss.utils.run_command(cmd)
        if not result:
            raise Exception(f"{cmd} failed")
        return result

    def append_values(self, time_step, store_nan=False):
        filename = self._run_command()
        self.parse_file(filename)
        self._append_func(time_step, store_nan=store_nan)

    def _append_values(self, time_step, store_nan=False):
        if not self._containers:
            for prop in self._properties.values():
                if prop.window_sizes and prop.is_moving_average():
                    # This is somewhat ugly code to allow different
                    # sizes for different element types collected in the same
                    # OpenDSS report.
                    window_sizes = self._get_window_size_by_name_index(prop)
                else:
                    window_sizes = None
                path = f"{self._base_path}/{self.element_class()}/ElementProperties/{prop.storage_name}"
                self._containers[prop.store_values_type] = self.make_storage_container(
                    path,
                    prop,
                    self._num_steps,
                    self._max_chunk_bytes,
                    self._values,
                    window_sizes=window_sizes,
                )

        if store_nan:
            for i in range(len(self._values)):
                self._values[i].set_nan()

        for sv_type, prop in self._properties.items():
            self._containers[sv_type].append_values(self._values, time_step)

    def _append_summed_values(self, time_step, store_nan=False):
        if store_nan:
            return

        self._values[0].set_value(sum([x.value for x in self._values]))

        prop = next(iter(self._properties.values()))
        if not self._containers:
            if len(self._properties) > 1:
                raise InvalidConfiguration("summing elements only supports one Property")
            assert len(self._properties) == 1
            assert prop.store_values_type in (StoreValuesType.ALL, StoreValuesType.SUM)
            path = (
                f"{self._base_path}/{prop.elem_class}/SummedElementProperties/{prop.storage_name}"
            )
            self._containers[prop.store_values_type] = self.make_storage_container(
                path,
                prop,
                self._num_steps,
                self._max_chunk_bytes,
                self._values,
            )

        self._containers[prop.store_values_type].append_values(self._values, time_step)

    def _check_output(self):
        filename = self._run_command()
        df = pd.read_csv(filename)
        for index, val in self.expected_column_headers().items():
            if df.columns[index].strip() != val:
                raise Exception(
                    f"Unexpected format in export file file: {index} {val} {df.columns}"
                )

    @staticmethod
    def _get_name_from_line(fields):
        return fields[0].strip()[1:-1]

    def _get_window_size_by_name_index(self, prop):
        """Returns a list of window sizes per element name corresponding to self._names."""
        if not prop.opendss_classes:
            raise InvalidConfiguration(f"window_sizes requires opendss_classes: {prop.name}")

        window_sizes = [None] * len(self._names)
        for opendss_class, window_size in prop.window_sizes.items():
            if opendss_class not in prop.opendss_classes:
                raise InvalidConfiguration(
                    f"{opendss_class} is not defined in opendss_classes: {prop.name}"
                )

        # Note: names have singluar class names, such as Line.line1.
        # opendss_classes are plural, such as Lines
        mapping = {}
        for i, name in enumerate(self._names):
            opendss_class_singular = name.split(".")[0]
            size = mapping.get(opendss_class_singular)
            if size is None:
                for opendss_class in prop.opendss_classes:
                    if opendss_class.startswith(opendss_class_singular):
                        size = prop.window_sizes[opendss_class]
                        mapping[opendss_class_singular] = size
            if size is None:
                raise InvalidConfiguration(f"Failed to find window_size for {name}")
            window_sizes[i] = size

        return window_sizes

    @staticmethod
    @abc.abstractmethod
    def element_class():
        """Return the element class."""

    @staticmethod
    @abc.abstractmethod
    def expected_column_headers():
        """Return the expected column headers in the CSV file."""

    @abc.abstractmethod
    def export_command(self):
        """Return the command to run in OpenDSS."""

    @staticmethod
    @abc.abstractmethod
    def label():
        """Return the label to use in dataframe columns."""

    @staticmethod
    def is_circuit_wide():
        return True

    def iter_containers(self):
        for sv_type in self._properties:
            if sv_type in self._containers:
                yield self._containers[sv_type]

    def iter_empty_containers(self):
        for prop in self._properties.values():
            if prop.store_values_type not in self._containers:
                yield prop

    @abc.abstractmethod
    def parse_file(self, filename):
        """Parse data in filename."""

    @staticmethod
    @abc.abstractmethod
    def requires_upper_case():
        """Return True if the names are upper case."""


class ExportLoadingsMetric(OpenDssExportMetric):
    """Stores line and transformer loading percentages in HDF5."""

    @staticmethod
    def element_class():
        return "CktElement"

    @staticmethod
    def expected_column_headers():
        return {0: "Name", 2: "%normal"}

    def export_command(self):
        filename = Path(self._tmp_dir) / "opendss_loading.csv"
        return f"export capacity {filename}"

    @staticmethod
    def label():
        return "Loading"

    @staticmethod
    def _get_name_from_line(fields):
        return fields[0].strip()

    def parse_file(self, filename):
        count = 0
        with open(filename) as f_in:
            # Skip the header.
            next(f_in)
            for line in f_in:
                fields = line.split(",")
                name = self._get_name_from_line(fields)
                if name in self._names:
                    index = self._names[name]
                    val = float(fields[2].strip())
                    self._values[index].set_value_from_raw(val)
                    count += 1
                else:
                    # There may be other element types that are not being tracked.
                    continue
        assert count == len(self._names), f"count={count} num_names={len(self._names)}"

    @staticmethod
    def requires_upper_case():
        return True


class ExportPowersMetric(OpenDssExportMetric):
    """Stores power values in HDF5."""

    @staticmethod
    def element_class():
        return "CktElement"

    def export_command(self):
        filename = Path(self._tmp_dir) / "opendss_powers.csv"
        return f"export powers {filename}"

    @staticmethod
    def expected_column_headers():
        return {0: "Element", 1: "Terminal", 2: "P(kW)"}

    @staticmethod
    def label():
        return "Powers"

    def parse_file(self, filename):
        data = {}
        with open(filename) as f_in:
            # Skip the header.
            next(f_in)
            for line in f_in:
                fields = line.split(",")
                name = self._get_name_from_line(fields)
                if name in self._names:
                    terminal = int(fields[1])
                    if terminal == 1:
                        val = abs(float(fields[2].strip()))
                        data[name] = val

        for name, val in data.items():
            index = self._names[name]
            self._values[index].set_value_from_raw(val)

    @staticmethod
    def requires_upper_case():
        return True


class OverloadsMetricInMemory(OpenDssExportMetric):
    """Stores line and transformer loading percentages in memory."""

    def __init__(self, prop, dss_objs, settings):
        super().__init__(prop, dss_objs, settings)
        # Indices for node names are tied to indices for node voltages.
        self._transformer_index = None
        self._discovered_elements = False
        start_time = get_start_time(settings)
        sim_resolution = get_simulation_resolution(settings)
        inputs = ReportBase.get_inputs_from_defaults(settings, "Thermal Metrics")
        line_window_size, transformer_window_size = self._get_window_sizes(inputs, sim_resolution)
        self._thermal_metrics = ThermalMetrics(
            prop,
            start_time,
            sim_resolution,
            line_window_size_hours=inputs["line_window_size_hours"],
            line_window_size=line_window_size,
            transformer_window_size_hours=inputs["transformer_window_size_hours"],
            transformer_window_size=transformer_window_size,
            line_loading_percent_threshold=inputs["line_loading_percent_threshold"],
            line_loading_percent_moving_average_threshold=inputs[
                "line_loading_percent_moving_average_threshold"
            ],
            transformer_loading_percent_threshold=inputs["transformer_loading_percent_threshold"],
            transformer_loading_percent_moving_average_threshold=inputs[
                "transformer_loading_percent_moving_average_threshold"
            ],
            store_per_element_data=inputs["store_per_element_data"],
        )

    def _append_values(self, time_step, store_nan=False):
        if not self._discovered_elements:
            line_names = []
            transformer_names = []
            for i, val in enumerate(self._values):
                if val.name.startswith("Line"):
                    line_names.append(val.name)
                elif val.name.startswith("Transformer"):
                    assert i != 0
                    transformer_names.append(val.name)
                    if self._transformer_index is None:
                        self._transformer_index = i
                else:
                    assert False, val.name
            self._thermal_metrics.line_names = line_names
            self._thermal_metrics.transformer_names = transformer_names
            self._discovered_elements = True

        if self._transformer_index is None:
            # There are no transformers.
            line_loadings = self._values[:]
            transformer_loadings = []
        else:
            line_loadings = self._values[: self._transformer_index]
            transformer_loadings = self._values[self._transformer_index :]

        if not store_nan:
            self._thermal_metrics.update(time_step, line_loadings, transformer_loadings)

        self._thermal_metrics.increment_steps()

    @staticmethod
    def _get_window_sizes(inputs, resolution):
        line_window_size = timedelta(hours=inputs["line_window_size_hours"])
        if line_window_size % resolution != timedelta(0):
            raise InvalidConfiguration(
                f"line_window_size={line_window_size} must be a multiple of {resolution}"
            )
        transformer_window_size = timedelta(hours=inputs["transformer_window_size_hours"])
        if transformer_window_size % resolution != timedelta(0):
            raise InvalidConfiguration(
                f"transformer_window_size={transformer_window_size} must be a multiple of {resolution}"
            )
        line_window_size = int(line_window_size / resolution)
        transformer_window_size = int(transformer_window_size / resolution)
        return line_window_size, transformer_window_size

    def close(self):
        path = os.path.join(
            str(self._settings.project.active_project_path),
            "Exports",
            self._settings.project.active_scenario,
        )
        self._thermal_metrics.generate_report(path)

    @staticmethod
    def element_class():
        return "CktElement"

    @staticmethod
    def expected_column_headers():
        return {0: "Name", 2: "%normal"}

    def export_command(self):
        filename = Path(self._tmp_dir) / "opendss_capacity.csv"
        return f"export capacity {filename}"

    @staticmethod
    def _get_name_from_line(fields):
        return fields[0].strip()

    @staticmethod
    def label():
        return "Overloads"

    def parse_file(self, filename):
        with open(filename) as f_in:
            # Skip the header.
            next(f_in)
            for line in f_in:
                fields = line.split(",")
                name = self._get_name_from_line(fields)
                if name in self._names:
                    index = self._names[name]
                    val = float(fields[2].strip())
                    self._values[index].set_value_from_raw(val)

    @staticmethod
    def requires_upper_case():
        return True


def convert_data(name, prop_name, value, conversion):
    if conversion == DataConversion.ABS:
        converted = copy.deepcopy(value)
        if isinstance(value.value, list):
            converted.set_value([abs(x) for x in value.value])
        else:
            converted.set_value(abs(value.value))
    elif conversion == DataConversion.SUM:
        converted = ValueByNumber(name, prop_name, sum(value.value))
    elif conversion == DataConversion.ABS_SUM:
        converted = ValueByNumber(name, prop_name, abs(sum(value.value)))
    elif conversion == DataConversion.SUM_REAL:
        converted = ValueByNumber(name, prop_name, sum((x.real for x in value.value)))
    elif conversion == DataConversion.SUM_ABS_REAL:
        converted = ValueByNumber(name, prop_name, sum((abs(x.real) for x in value.value)))
    else:
        converted = value

    return converted


# Bus and Circuit are excluded.
_OPEN_DSS_CLASS_FOR_ITERATION = {
    "Capacitor": dss.Capacitors,
    "Fuse": dss.Fuses,
    "Generator": dss.Generators,
    "Isource": dss.Isource,
    "Line": dss.Lines,
    "Load": dss.Loads,
    "Meter": dss.Meters,
    "Monitor": dss.Monitors,
    "PVSystem": dss.PVsystems,
    "Recloser": dss.Reclosers,
    "RegControl": dss.RegControls,
    "Relay": dss.Relays,
    "Sensor": dss.Sensors,
    "Transformer": dss.Transformers,
    "Vsource": dss.Vsources,
    "XYCurve": dss.XYCurves,
}
