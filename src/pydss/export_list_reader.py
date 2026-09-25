from collections import defaultdict
from pathlib import Path
import os
import re

from loguru import logger


from pydss.common import DataConversion, LimitsFilter, StoreValuesType, DatasetPropertyType, MinMax
from pydss.py_contr_reader import PyExportReader
from pydss.utils.utils import load_data
from pydss.exceptions import InvalidConfiguration, InvalidParameter
from pydss.metrics import (
    NodeVoltageMetric,
    TrackCapacitorChangeCounts,
    TrackRegControlTapNumberChanges,
    ExportLoadingsMetric,
    OverloadsMetricInMemory,
    ExportPowersMetric,
    FeederHeadMetrics,
)


CUSTOM_METRICS = {
    "Capacitors.TrackStateChanges": TrackCapacitorChangeCounts,
    "CktElement.ExportLoadingsMetric": ExportLoadingsMetric,
    "CktElement.OverloadsMetricInMemory": OverloadsMetricInMemory,
    "CktElement.ExportPowersMetric": ExportPowersMetric,
    "FeederHead.FeederHeadMetrics": FeederHeadMetrics,
    # "Lines.LoadingPercent": LineLoadingPercent,
    "Nodes.VoltageMetric": NodeVoltageMetric,
    "RegControls.TrackTapNumberChanges": TrackRegControlTapNumberChanges,
    # "Transformers.LoadingPercent": TransformerLoadingPercent,
}


class ExportListProperty:
    """Contains export options for an element property."""

    def __init__(self, elem_class, data):
        self.elem_class = elem_class
        self._opendss_classes = data.get("opendss_classes", [])
        self.name = data["property"]
        self.publish = data.get("publish", False)
        self._data_conversion = DataConversion(data.get("data_conversion", "none"))
        self._sum_elements = data.get("sum_elements", False)
        self._sum_groups = data.get("sum_groups", [])
        sum_groups_file = data.get("sum_groups_file")
        self._limits = self._parse_limits(data, "limits")
        self._limits_filter = LimitsFilter(data.get("limits_filter", "outside"))
        self._limits_b = self._parse_limits(data, "limits_b")
        self._limits_filter_b = LimitsFilter(data.get("limits_filter_b", "outside"))
        self._store_values_type = StoreValuesType(data.get("store_values_type", "all"))
        self._names, self._are_names_regex, self._are_names_filtered = self._parse_names(data)
        self._sample_interval = data.get("sample_interval", 1)
        self._window_size = data.get("window_size", 100)
        self._window_sizes = data.get("window_sizes", {})
        custom_prop = f"{elem_class}.{self.name}"
        self._custom_metric = CUSTOM_METRICS.get(custom_prop)

        if self._sum_groups or sum_groups_file:
            self._check_sum_groups(sum_groups_file)

        # Note to devs: any field added here needs to be handled in serialize()

        if self._sum_elements and self._store_values_type not in (
            StoreValuesType.ALL,
            StoreValuesType.SUM,
        ):
            raise InvalidConfiguration("sum_elements requires store_values_types = all or sum")

        if self._is_max() and self._limits is not None:
            raise InvalidConfiguration("limits are not allowed with max types")

        requires_opendss_classes = (
            "ExportLoadingsMetric",
            "OverloadsMetricInMemory",
            "ExportPowersMetric",
        )
        if (
            elem_class == "CktElement"
            and self.name in requires_opendss_classes
            and not self._opendss_classes
        ):
            raise InvalidConfiguration(
                f"Exporting {elem_class}.{self.name} requires that opendss_classes be specifed"
            )

    def _check_sum_groups(self, sum_groups_file):
        if sum_groups_file is not None:
            if self._sum_groups:
                raise InvalidConfiguration("Cannot set both sum_groups and sum_groups_file")

            # This path needs to be relative to the current directory, not the Exports.toml.
            # This might need to be changed.
            if not Path(sum_groups_file).exists():
                raise InvalidConfiguration(
                    f"{sum_groups_file} does not exist. The path must be relative to the current directory."
                )
            self._sum_groups = load_data(sum_groups_file)["sum_groups"]

        self._sum_elements = True  # Ignore the user setting. This must be true.
        # Ensure that there are no duplicate names.
        orig_length = 0
        all_names = set()
        for group in self._sum_groups:
            orig_length += len(group["elements"])
            group["elements"] = set(group["elements"])
            all_names = all_names.union(group["elements"])
        if orig_length != len(all_names):
            tag = f"{self.elem_class}/{self.name}"
            raise InvalidConfiguration(f"{tag} has duplicate element names in sum_groups")

    def _is_max(self):
        return self._store_values_type in (
            StoreValuesType.MAX,
            StoreValuesType.MOVING_AVERAGE_MAX,
        )

    @property
    def are_names_filtered(self):
        return self._are_names_filtered

    def is_moving_average(self):
        return self._store_values_type in (
            StoreValuesType.MOVING_AVERAGE,
            StoreValuesType.MOVING_AVERAGE_MAX,
        )

    @staticmethod
    def _parse_limits(data, field_name):
        limits = data.get(field_name)
        if limits is None:
            return None

        if not isinstance(limits, list) or len(limits) != 2:
            raise InvalidConfiguration(f"invalid limits format: {limits}")

        return MinMax(limits[0], limits[1])

    @staticmethod
    def _parse_names(data):
        names = data.get("names")
        name_regexes = data.get("name_regexes")

        if names and name_regexes:
            raise InvalidConfiguration("names and name_regexes cannot both be set")
        for obj in (names, name_regexes):
            if obj is None:
                continue
            if not isinstance(obj, list) or not isinstance(obj[0], str):
                raise InvalidConfiguration(f"invalid name format: {obj}")

        if names:
            return set(names), False, True
        if name_regexes:
            return [re.compile(r"{}".format(x)) for x in name_regexes], True, True

        return None, False, False

    def _is_inside_limits(self, value):
        """Return True if the value is between min and max, inclusive."""
        return value >= self._limits.min and value <= self._limits.max

    def _is_outside_limits(self, value):
        """Return True if the value is lower than min or greater than max."""
        return value < self._limits.min or value > self._limits.max

    def append_opendss_classes(self, opendss_classes):
        """Append all opendss_classes from a list."""
        self._opendss_classes[:] = list(set(self._opendss_classes + opendss_classes))

    @property
    def custom_metric(self):
        """Return the custom_metric attribute.

        Returns
        -------
        Metric | None

        """
        return self._custom_metric

    @property
    def data_conversion(self):
        """Return the data_conversion attribute

        Returns
        -------
        DataConversion

        """
        return self._data_conversion

    def get_dataset_property_type(self):
        """Return the encoding to use for the dataset backing these values.

        Returns
        -------
        DatasetPropertyType

        """
        if self._limits is not None:
            return DatasetPropertyType.FILTERED
        if self._store_values_type in (
            StoreValuesType.SUM,
            StoreValuesType.MAX,
            StoreValuesType.MIN,
            StoreValuesType.MOVING_AVERAGE_MAX,
            StoreValuesType.CHANGE_COUNT,
        ):
            return DatasetPropertyType.VALUE
        return DatasetPropertyType.PER_TIME_POINT

    def get_max_size(self, num_steps):
        """Return the max number of items that could be stored."""
        singles = (
            StoreValuesType.CHANGE_COUNT,
            StoreValuesType.MAX,
            StoreValuesType.MIN,
            StoreValuesType.MOVING_AVERAGE_MAX,
            StoreValuesType.SUM,
        )
        if self._store_values_type in singles:
            return 1
        num_samples = num_steps / self._sample_interval
        return int(num_samples)

    @property
    def limits(self):
        """Return the limits for the export property.

        Returns
        -------
        MinMax

        """
        return self._limits

    @property
    def limits_b(self):
        """Return the limits_b for the export property.

        Returns
        -------
        MinMax

        """
        return self._limits_b

    @property
    def opendss_classes(self):
        """Return the element classes to be used with the property.

        Returns
        -------
        list

        """
        return self._opendss_classes[:]

    def serialize(self):
        """Serialize object to a dictionary."""
        if self._are_names_regex:
            # raise InvalidConfiguration("cannot serialize when names are regex")
            logger.warning("cannot serialize when names are regex")
            names = None
        else:
            names = self._names
        data = {
            "property": self.name,
            "data_conversion": self._data_conversion.value,
            "opendss_classes": self._opendss_classes,
            "sample_interval": self._sample_interval,
            "names": names,
            "publish": self.publish,
            "store_values_type": self.store_values_type.value,
            "sum_elements": self.sum_elements,
            "sum_groups": self.sum_groups,
        }
        if self._limits is not None:
            data["limits"] = [self._limits.min, self._limits.max]
            data["limits_filter"] = self._limits_filter.value
        if self._limits_b is not None:
            data["limits_b"] = [self._limits_b.min, self._limits_b.max]
            data["limits_filter_b"] = self._limits_filter_b.value
        if self.is_moving_average():
            if self.window_sizes:
                data["window_sizes"] = self._window_sizes
                if not self._opendss_classes:
                    raise InvalidConfiguration(
                        f"window_sizes requires opendss_classes: {self.name}"
                    )
            else:
                data["window_size"] = self._window_size

        return data

    def should_store_name(self, name):
        """Return True if name matches the input criteria."""
        if self._names is None:
            return True

        if self._are_names_regex:
            for regex in self._names:
                if regex.search(name):
                    return True
            return False

        return name in self._names

    def should_sample_value(self, step_number):
        """Return True if it's time to read a new value."""
        return step_number % self._sample_interval == 0

    def should_store_value(self, value):
        """Return True if the value meets the input criteria."""
        if self._limits is None:
            return True

        if self._limits_filter == LimitsFilter.OUTSIDE:
            return self._is_outside_limits(value)
        return self._is_inside_limits(value)

    def should_store_time_step(self):
        """Return True if the time step should be stored with the value."""
        return self.limits is not None

    @property
    def storage_name(self):
        if self._store_values_type in (StoreValuesType.ALL, StoreValuesType.CHANGE_COUNT):
            return self.name
        if self._store_values_type == StoreValuesType.MOVING_AVERAGE:
            return self.name + "Avg"
        if self._store_values_type == StoreValuesType.MOVING_AVERAGE_MAX:
            return self.name + "AvgMax"
        if self._store_values_type == StoreValuesType.MAX:
            return self.name + "Max"
        if self._store_values_type == StoreValuesType.MIN:
            return self.name + "Min"
        if self._store_values_type == StoreValuesType.SUM:
            return self.name + "Sum"
        assert False

    @property
    def store_values_type(self):
        """Return the type of storage for this property."""
        return self._store_values_type

    @property
    def sum_elements(self):
        """Return True if the value is the sum of all elements."""
        return self._sum_elements

    @property
    def sum_groups(self):
        """Return the groups of element names to sum.

        Returns
        -------
        list

        """
        return self._sum_groups

    @property
    def window_size(self):
        """Return the window size for moving averages.

        Returns
        -------
        int

        """
        return self._window_size

    @property
    def window_sizes(self):
        """Return window sizes for moving averages. Tied to opendss_classes.

        Returns
        -------
        dict

        """
        return self._window_sizes


class ExportListReader:
    """Reads export files and provides access to export properties."""

    def __init__(self, filename):
        self._elem_classes = defaultdict(list)
        legacy_files = ("ExportMode-byClass.toml", "ExportMode-byElement.toml")
        if os.path.basename(filename) in legacy_files:
            parser = self._parse_legacy_file
        else:
            parser = self._parse_file

        for elem_class, data in parser(filename):
            self._elem_classes[elem_class].append(ExportListProperty(elem_class, data))

        # TODO: verify that multiple instances of the same property have
        # the same names.

    @staticmethod
    def _parse_file(filename):
        data = load_data(filename)
        for elem_class, prop_info in data.items():
            if isinstance(prop_info, list):
                for prop in prop_info:
                    yield elem_class, prop
            else:
                assert isinstance(prop_info, dict)
                for prop, values in prop_info.items():
                    new_data = {"property": prop, **values}
                    yield elem_class, new_data

    @staticmethod
    def _parse_legacy_file(filename):
        reader = PyExportReader(filename)
        publications = {tuple(x.split()) for x in reader.publicationList}
        for elem_class, props in reader.pyControllers.items():
            for prop in props:
                publish = (elem_class, prop) in publications
                yield elem_class, {"property": prop, "publish": publish}

    def append_property(self, elem_class, prop_data):
        self._elem_classes[elem_class].append(ExportListProperty(elem_class, prop_data))

    def get_element_properties(self, elem_class, prop):
        if elem_class not in self._elem_classes:
            raise InvalidParameter(f"{elem_class} is not stored")
        return [x for x in self._elem_classes[elem_class] if x.name == prop]

    def iter_export_properties(self, elem_class=None):
        """Returns a generator over the ExportListProperty objects.

        Yields
        ------
        ExportListProperty

        """
        if elem_class is None:
            for props in self._elem_classes.values():
                for prop in props:
                    yield prop
        elif elem_class not in self._elem_classes:
            raise InvalidParameter(f"{elem_class} is not stored")
        else:
            for prop in self._elem_classes[elem_class]:
                yield prop

    def list_element_classes(self):
        return sorted(list(self._elem_classes.keys()))

    def list_element_properties(self, elem_class):
        if elem_class not in self._elem_classes:
            return []
        return self._elem_classes[elem_class]

    def list_element_property_names(self, elem_class):
        return sorted({x.name for x in self._elem_classes[elem_class]})

    # This compatibility property matches the legacy PyExportReader interface.
    @property
    def publication_list(self):
        """Return the properties to be published to HELICS.

        Returns
        -------
        list
            Format: ["ElementClass Property"]

        """
        return [f"{x.elem_class} {x.name}" for x in self.iter_export_properties() if x.publish]

    def serialize(self):
        """Serialize object to a dictionary."""
        data = defaultdict(list)
        for elem_class, props in self._elem_classes.items():
            for prop in props:
                data[elem_class].append(prop.serialize())

        return data


setattr(ExportListReader, "publicationList", ExportListReader.publication_list)
