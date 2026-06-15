###############
HDF Data Format
###############
This page describes the format PyDSS uses to export data in an HDF file. PyDSS
contains code to convert the raw data to pandas.DataFrame objects or Python
dictionaries, so normal users should not need to write their own tools to
interpret the data.

Refer to :class:`pydss.pydss_results.PyDssResults` and
:class:`pydss.pydss_results.PyDssScenarioResults` for user-friendly interfaces.
They are also described in :ref:`tutorial:Analyze results`.

******
Layout
******
Each PyDSS project creates ``<project-path>/store.h5`` to store exported data
for all scenarios.

Each scenario's data is stored under ``Exports/<scenario-name>``.

Data stored for an element property for individual elements is stored in an HDF
dataset. ::

    Exports/<scenario-name>/<element-class>/ElementProperties/<property-name>

This dataset includes columns for each individual element.

Data stored for an element property across elements of a given type is stored
in an HDF dataset ::

    Exports/<scenario-name>/<element-class>/SummedElementProperties/<property-name>

Data stored for an element property across elements of a given type split by
element name are stored in an HDF dataset ::

    Exports/<scenario-name>/<element-class>/SummedElementProperties/<property-name>__<group>

If a property is configured to compute a moving average, sum, min, or max on
the data then a suffix is added to the property name.

- ``<property-name>/Avg``
- ``<property-name>/Max``
- ``<property-name>/Min``
- ``<property-name>/Sum``

Common Metadata
===============
PyDSS stores metadata that is common to all datasets in the root of the
scenario group. For example, the ``Timestamp`` dataset contains the simulation
timestamps (seconds since epoch) for all datasets that store values at every
time point. ::

    Exports/<scenario-name>/Timestamp
    Exports/<scenario-name>/Frequency
    Exports/<scenario-name>/Mode

Dataset Metadata
================
PyDSS stores metadata for each dataset in HDF attributes as well as other
datasets. This metadata describes the contents of datasets.

Attributes per dataset
----------------------

- ``type``: Describes what type of data is stored.

  - ``per_time_point``:  Data is stored at every time point; indices are
    shared.
  - ``value``:  Only a single value is stored for each element.
  - ``filtered``:  Data is stored after being filtered; indices are stored for
    each element.
  - ``metadata``:  Metadata for another dataset.
  - ``time_step``:  Data are time indices, tied to ``filtered``.

- ``length``: Number of rows of valid data written to the dataset.

Metadata datasets per dataset
-----------------------------
These items are stored in datasets because they exceed the max size for
attributes when the number of elements is larger than approximately 1000.

- <property-name>ColumnRanges: Range of column indices for each element
- <property-name>Columns: Column names for element, including units
- <property-name>Names: Name of each element stored in the dataset. Order is
  the same as in ``ColumnRanges`` and ``Columns``.

If a dataset is ``filtered`` then then the dataset has a single column that
includes all elements. Another dataset contains metadata to describe the
contents. This dataset has ``TimeStep`` appended to the property name. Each
row of this dataset is an array where the first item is the
simulation time step number and the second is the element index. The element
indices follow the same order as the ``Names`` and ``Columns`` datasets described above.

For example, suppose ``Nodes.VoltageMetric`` is stored with limits of ``[0.95,
1.05]`` and the only violations are at time step 90 on nodes 4 and 5. The
contents of this dataset would be::

    Exports/<scenario-name>/Nodes/ElementProperties/VoltageMetricTimeStep

    [[90, 4], [90, 5]]

********
Examples
********
The HDF Group provides graphical and command-line tools to browse HDF files.
They can be downloaded from https://support.hdfgroup.org/products/hdf5_tools/

::

    # Run a test project.
    pydss run tests/data/custom_exports_project

    # View the raw data in the HDF file.

    h5ls -r tests/data/custom_exports_project/store.h5 | grep Timestamp

    /Exports/scenario1/Timestamp Dataset {96, 1}
    /Exports/scenario1/TimestampColumns Dataset {1}

    h5ls -r tests/data/custom_exports_project/store.h5 | grep LineLosses

    /Exports/scenario1/Circuits/ElementProperties/LineLosses Dataset {96, 1}
    /Exports/scenario1/Circuits/ElementProperties/LineLossesColumnRanges Dataset {1, 2}
    /Exports/scenario1/Circuits/ElementProperties/LineLossesColumns Dataset {1}
    /Exports/scenario1/Circuits/ElementProperties/LineLossesNames Dataset {1}
