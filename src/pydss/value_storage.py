
import abc
import os
import re

from loguru import logger
import numpy as np

from pydss.common import DatasetPropertyType, INTEGER_NAN
from pydss.dataset_buffer import DatasetBuffer
from pydss.exceptions import InvalidParameter, InvalidConfiguration


class ValueStorageBase(abc.ABC):

    DELIMITER = "__"

    def __init__(self):
        self._dataset = None

    @staticmethod
    def get_columns(df, names, options, **kwargs):
        """Return the column names in the dataframe that match names and kwargs.

        Parameters
        ----------
        df : pd.DataFrame
        names : str | list
            single name or list of names
        kwargs : dict
            Filter on options; values can be strings or regular expressions.

        Returns
        -------
        list

        """
        if isinstance(names, str):
            names = set([names])
        elif isinstance(names, set):
            pass
        else:
            names = set(names)
        field_indices = {option: i + 1 for i, option in enumerate(options)}
        columns = []
        for column in df.columns:
            col = column
            index = column.find(" [")
            if index != -1:
                col = column[:index]
            # [name, option1, option2, ...]
            fields = ValueStorageBase.get_fields(col, next(iter(names)))
            if options and kwargs:
                assert len(fields) == 1 + len(options), f"fields={fields} options={options}"
            _name = fields[0]
            if _name not in names:
                continue
            match = True
            for key, val in kwargs.items():
                if isinstance(val, str):
                    if fields[field_indices[key]] != val:
                        match = False
                elif isinstance(val, re.Pattern):
                    if val.search(fields[field_indices[key]]) is None:
                        match = False
                elif val is None:
                    continue
                else:
                    raise InvalidParameter(f"unhandled option value '{val}'")
                if not match:
                    break
            if match:
                columns.append(column)

        if not columns:
            raise InvalidParameter(f"{names} does not exist in DataFrame")

        return columns

    @staticmethod
    def get_option_values(df, name):
        """Return the option values parsed from the column names.

        Parameters
        ----------
        df : pd.DataFrame
        name : str

        Returns
        -------
        list

        """
        values = []
        for column in df.columns:
            col = column
            index = column.find(" [")
            if index != -1:
                col = column[:index]
            # [name, option1, option2, ...]
            fields = ValueStorageBase.get_fields(col, name)
            _name = fields[0]
            if _name != name:
                continue
            values += fields[1:]

        if not values:
            raise InvalidParameter(f"{name} does not exist in DataFrame")

        return values

    @staticmethod
    def get_fields(col, name):
        # Handle case where the name ends with part of the DELIMITER.
        col_tmp = col.replace(name, "", 1)
        fields = col_tmp.split(ValueStorageBase.DELIMITER)[1:]
        fields.insert(0, name)
        return fields

    @abc.abstractmethod
    def is_nan(self):
        """Return True if the value is NaN.

        Returns
        -------
        bool

        """

    @abc.abstractmethod
    def make_columns(self):
        """Return a list of column names

        Returns
        -------
        list

        """

    @property
    def name(self):
        return self._name

    @property
    @abc.abstractmethod
    def num_columns(self):
        """Return the number of columns in the data.

        Returns
        -------
        int

        """

    @abc.abstractmethod
    def set_element_property(self, prop):
        """Set the element property name.

        Parameters
        ----------
        prop : str

        """

    @abc.abstractmethod
    def set_name(self, name):
        """Set the name.

        Parameters
        ----------
        name : str

        """

    @abc.abstractmethod
    def set_nan(self):
        """Set the value to NaN or equivalent."""

    @abc.abstractmethod
    def set_value(self, value):
        """Set the value from another instance.

        Parameters
        ----------
        value : ValueStorageBase

        """

    @abc.abstractmethod
    def set_value_from_raw(self, value):
        """Set the value from a new raw value from opendssdirect.

        Parameters
        ----------
        value : list | float | complex

        """

    @property
    @abc.abstractmethod
    def value(self):
        """Return the value.

        Returns
        -------
        list | float | complex

        """

    @property
    @abc.abstractmethod
    def value_type(self):
        """Return the type of value being stored.

        Returns
        -------
        Type

        """


class ValueByList(ValueStorageBase):
    """"Stores a list of lists of numbers by an arbitrary suffix. This is a generic method to handle lists returned from
    a function call. An example would be returned values "taps" function for transformer elements. The class can be
    used for any methods that return a list.
    """
    def __init__(self, name, prop, values, label_suffixes):
        """Constructor for ValueByLabel

        Parameters
        ----------
        name : str
        prop : str
        label_prefix : str
            Text to use as a prefix for column labels. Ex: Phase
        labels : list
            list of str
        values : list
            Pairs of values that can be interpreted as complex numbers.

        """
        super().__init__()
        self._name = name
        self._prop = prop
        self._labels = []
        self._value_type = None
        self._value = []
        assert (isinstance(values, list) and len(values) == len(label_suffixes)), \
            '"values" and "label_suffixes" should be lists of equal lengths'
        for val, lab_suf in zip(values, label_suffixes):
            label = prop + self.DELIMITER + lab_suf
            self._labels.append(label)
            self._value.append(val)
            if self._value_type is None:
                self._value_type = type(val)

    def __iadd__(self, other):
        for i in range(len(self._value)):
            self._value[i] += other.value[i]
        return self

    def __gt__(self, other):
        # TODO
        return sum(self._value) > sum(other.value)

    def is_nan(self):
        if np.issubdtype(self._value_type, np.int64):
            return self._value[0] == INTEGER_NAN
        return np.isnan(self._value[0])

    def make_columns(self):
        return [
            self.DELIMITER.join((self._name, f"{x}")) for x in self._labels
        ]

    @property
    def num_columns(self):
        return len(self._labels)

    def set_element_property(self, prop):
        self._prop = prop

        # Update the property inside each label.
        for i, label in enumerate(self._labels):
            fields = label.split(self.DELIMITER)
            assert len(fields) == 2
            fields[0] = prop
            self._labels[i] = self.DELIMITER.join(fields)

    def set_name(self, name):
        self._name = name

    def set_nan(self):
        for i in range(len(self._value)):
            self._value[i] = np.nan

    def set_value(self, value):
        self._value = value
        if not isinstance(value[0], self._value_type):
            self._value_type = type(value[0])

    def set_value_from_raw(self, value):
        self._value = value

    @property
    def value(self):
        return self._value

    @property
    def value_type(self):
        return self._value_type


class ValueByNumber(ValueStorageBase):
    """Stores a list of numbers for an element/property."""
    def __init__(self, name, prop, value):
        super().__init__()
        assert not isinstance(value, list), str(value)
        self._name = name
        self._prop = prop
        self._value_type = type(value)
        if self._value_type == str:
            raise InvalidConfiguration(
                f"Data export feature does not support strings: name={name} prop={prop} value={value}"
            )
        self._value = value
        self._is_complex = isinstance(self._value_type, complex)

    def __iadd__(self, other):
        self._value += other.value
        return self

    def __gt__(self, other):
        return self._value > other.value

    def is_nan(self):
        if np.issubdtype(self._value_type, np.int64):
            return self._value == INTEGER_NAN
        return np.isnan(self._value)

    def make_columns(self):
        return [ValueStorageBase.DELIMITER.join((self._name, self._prop))]

    @property
    def num_columns(self):
        return 1

    def set_element_property(self, prop):
        self._prop = prop

    def set_name(self, name):
        self._name = name

    def set_nan(self):
        if np.issubdtype(self._value_type, np.int64):
            self._value = INTEGER_NAN
        else:
            self._value = np.nan

    def set_value(self, value):
        self._value = value
        if not isinstance(value, self._value_type):
            self._value_type = type(value)

    def set_value_from_raw(self, value):
        self._value = value

    @property
    def value(self):
        return self._value

    @property
    def value_type(self):
        return self._value_type


class ValueByLabel(ValueStorageBase):
    """Stores a list of lists of numbers by an arbitrary label. Use this class when working with cktElement function
    calls like Currents, currentMagAng where every two consecutive values in the returned list are representing one
    quantity. The class differentiates between complex and mag / angle representation and stores the values appropriately
    """
    def __init__(self, name, prop, value, Nodes, is_complex, units):
        """Constructor for ValueByLabel

        Parameters
        ----------
        name : str
        prop : str
        label_prefix : str
            Text to use as a prefix for column labels. Ex: Phase
        labels : list
            list of str
        values : list
            Pairs of values that can be interpreted as complex numbers.

        """
        super().__init__()
        phs = {
            1: 'A',
            2: 'B',
            3: 'C',
            0: 'N',
        }

        self._name = name
        self._prop = prop
        self._nodes = Nodes
        self._labels = []
        self._value = []
        self._value_type = complex if is_complex else float
        self._is_complex = is_complex

        n = 2
        m = int(len(value) / (len(Nodes)*n))

        self._m = m
        self._n = n
        self._value_length = len(value)
        value = self._fix_value(value)
        
        # Chunk_list example
        # X = list(range(12)) , nList= 2
        # Y = chunk_list(X, nList) -> [[0, 1], [2, 3], [4, 5], [6, 7], [8, 9], [10, 11]]
        # Given element has 2 terminals m = 12 / (2*2) = 3
        # Z =  chunk_list(Y, m) - > [
        #                            [[0, 1], [2, 3], [4, 5]],  Terminal one complex pairs
        #                            [[6, 7], [8, 9], [10, 11]] Terminal two complex pairs
        #                            ]

        for i, node_val in enumerate(zip(self._nodes, value)):
            node, val = node_val
            for v, x in zip(node, val):
                label = '{}{}'.format(phs[v], str(i+1))
                # Note that the value logic is duplicated in set_value_from_raw
                if self._is_complex:
                    label += " " + units[0]
                    self._labels.append(label)
                    self._value += [complex(x[0], x[1])]
                else:
                    label_mag = label + self.DELIMITER + "mag" + ' ' + units[0]
                    label_ang = label + self.DELIMITER + "ang" + ' ' + units[1]
                    self._labels.extend([label_mag, label_ang])
                    self._value += [x[0], x[1]]

    def __iadd__(self, other):
        for i in range(len(self._value)):
            self._value[i] += other.value[i]
        return self

    def __gt__(self, other):
        # TODO
        return sum(self._value) > sum(other.value)

    @property
    def value(self):
        return self._value

    @staticmethod
    def chunk_list(values, nLists):
        # TODO: this breaks for Bus.puVmagAngle in monte carlo example test
        return  [values[i * nLists:(i + 1) * nLists] for i in range((len(values) + nLists - 1) // nLists)]

    def _fix_value(self, value):
        value = self.chunk_list(value, self._n)
        value = self.chunk_list(value, self._m)
        return value

    def is_nan(self):
        if np.issubdtype(self._value_type, np.int64):
            return self._value[0] == INTEGER_NAN
        return np.isnan(self._value[0])

    def make_columns(self):
        return [
            self.DELIMITER.join((self._name, f"{x}")) for x in self._labels
        ]

    @property
    def num_columns(self):
        return len(self._labels)

    def set_element_property(self, prop):
        self._prop = prop

    def set_name(self, name):
        self._name = name

    def set_nan(self):
        for i in range(len(self._value)):
            self._value[i] = np.nan

    def set_value(self, value):
        self._value = value
        if not isinstance(value[0], self._value_type):
            self._value_type = type(value[0])

    def set_value_from_raw(self, value):
        if len(value) != self._value_length:
            value = [np.nan for i in range(self._value_length)]
        
        value = self._fix_value(value)
        self._value.clear()
        
        for i, node_val in enumerate(zip(self._nodes, value)):
            node, val = node_val
            for v, x in zip(node, val):
                if self._is_complex:
                    self._value += [complex(x[0], x[1])]
                else:
                    self._value += [x[0], x[1]]
    @property
    def value_type(self):
        return self._value_type


class ValueContainer:
    """Container for a sequence of instances of ValueStorageBase."""

    def __init__(self, values, hdf_store, path, max_size, elem_names,
                 dataset_property_type, max_chunk_bytes=None, store_time_step=False):
        group_name = os.path.dirname(path)
        basename = os.path.basename(path)
        self.group_name = group_name
        self.base_name = basename
        try:
            if basename in hdf_store[group_name]:
                raise InvalidParameter(f"duplicate dataset name {basename}")
        except KeyError:
            # Don't bother checking each sub path.
            pass
        
        self._length={}
        for value in values:
            if isinstance(value, list):
                self._length[value] = len(value.value)
            else:
                self._length[value] = 1
        
        dtype = values[0].value_type
        scaleoffset = None
        # There is no np.float128 on Windows.
        if dtype in (float, np.float32, np.float64, np.longdouble):
            scaleoffset = 4
        time_step_path = None
        max_size = max_size * len(values) if store_time_step else max_size

        if store_time_step:
            # Store indices for time step and element.
            # Each row of this dataset corresponds to a row in the data.
            # This will be required to interpret the raw data.
            attributes = {"type": DatasetPropertyType.TIME_STEP.value}
            time_step_path = self.time_step_path(path)
            self._time_steps = DatasetBuffer(
                hdf_store,
                time_step_path,
                max_size,
                int,
                ["Time", "Name"],
                scaleoffset=0,
                max_chunk_bytes=max_chunk_bytes,
                attributes=attributes,
            )
            columns = []
            tmp_columns = values[0].make_columns()
            for column in tmp_columns:
                fields = column.split(ValueStorageBase.DELIMITER)
                fields[0] = "AllNames"
                columns.append(ValueStorageBase.DELIMITER.join(fields))
            column_ranges = [0, len(tmp_columns)]
        else:
            columns = []
            column_ranges = []
            col_index = 0
            for value in values:
                tmp_columns = value.make_columns()
                col_range = (col_index, len(tmp_columns))
                column_ranges.append(col_range)
                for column in tmp_columns:
                    columns.append(column)
                    col_index += 1
            self._time_steps = None

        attributes = {"type": dataset_property_type.value}
        if store_time_step:
            attributes["time_step_path"] = time_step_path

        self._dataset = DatasetBuffer(
            hdf_store,
            path,
            max_size,
            dtype,
            columns,
            scaleoffset=scaleoffset,
            max_chunk_bytes=max_chunk_bytes,
            attributes=attributes,
            names=elem_names,
            column_ranges_per_name=column_ranges,
        )

    @staticmethod
    def time_step_path(path):
        return path + "TimeStep"

    def append(self, values):
        """Append a value to the container.

        Parameters
        ----------
        value : list
            list of ValueStorageBase

        """
        
        if values:
            if isinstance(values[0].value, list):
                vals = [x for y in values for x in y.value]
            else:
                vals = [INTEGER_NAN if (x.is_nan() and x._value_type == int) else x.value for x in values ]
        else:
            vals = [self.set_nan() for k, v in self._length.items() for x in range(v)]
        self._dataset.write_value(vals)
                     

    def append_by_time_step(self, value, time_step, elem_index):
        """Append a value to the container.

        Parameters
        ----------
        value : ValueStorageBase
        time_step : int
        elem_index : int

        """
        
        if isinstance(value.value, list):
            vals = [x for x in value.value]
        else:
            vals = value.value

        self._dataset.write_value(vals)
        self._time_steps.write_value([time_step, elem_index])
        
        
    def flush_data(self):
        """Flush any outstanding data to disk."""
        self._dataset.flush_data()
        if self._time_steps is not None:
            self._time_steps.flush_data()

    def max_num_bytes(self):
        """Return the maximum number of bytes the container could hold.

        Returns
        -------
        int

        """
        return self._dataset.max_num_bytes()


def get_dataset_property_type(dataset):
    """Return the property type of this dataset.

    Returns
    -------
    DatasetPropertyType

    """
    return DatasetPropertyType(dataset.attrs["type"])


def get_time_step_path(dataset):
    """Return the path to the time_steps for this dataset.

    Returns
    -------
    str

    """
    return dataset.attrs["time_step_path"]
