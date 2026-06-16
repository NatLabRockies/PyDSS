#######
Reports
#######
This page describes how to generate PyDSS reports from exported simulation data.

The following reports can be enabled in the project's ``simulation.toml``
``Reports`` section.

- Capacitor State Change Counts (``EXPERIMENTAL``): Reports the state changes per Capacitor.
- Feeder Losses: Reports the feeder losses.
- PV Clipping (``EXPERIMENTAL``): Reports PV Clipping for the simulation.
- PV Curtailment (``EXPERIMENTAL``): Reports PV Curtailment at every time point in the simulation.
- RegControl Tap Number Change Counts (``EXPERIMENTAL``): Reports the tap number changes per RegControl.
- Thermal Metrics: Reports thermal metrics.
- Voltage Metrics: Reports voltage metrics. 

The ``Reports`` section contains global settings that may apply to any report.
Each report may contain its own specific settings.

***************
Global settings
***************

Format
======
Used to control export format for dataframes: ``.csv`` or ``.h5``. In either
case you can use PyDSS to convert the file back to a dataframe.

.. code-block:: python

    from pydss.utils.dataframe_utils import read_dataframe

    df = read_dataframe("path/to/filename")

Granularity
===========
Controls how often and how much data is collected. This applies to elements of a
given type, such as PVSystems. Suppose there are 100 PVSystems in the circuit
and 35,040 time points in the simulation. Each value stored is a float that
consumes 8 bytes.

- ``per_element_per_time_point``: Collect data for every element at every time
  point.

  Storage required: 100 elements * 35040 floats * 8 bytes = 27 MiB
- ``per_element_total``: Keep a running sum for each element. Report the total
  for each element.

  Storage required: 100 elements * 1 float * 8 bytes = 800
  bytes
- ``all_elements_per_time_point``: Sum all elements for a given type at every
  time point.

  Storage required: 1 * 35040 floats * 8 bytes = 273 KiB
- ``all_elements_total``: Keep a running sum across all elements for a given
  type.

  Storage required: 1 element * 1 number = 8 bytes

*****************
Export Parameters
*****************
Each report configures its own export parameters. PyDSS will serialize the
export parameters used in a simulation to
``<project-path>/Exports/<scenario-name>/ExportsActual.toml``.

This can be useful for debugging purposes when you develop your own reports.

***********
Output Data
***********
PyDSS stores generated reports in ``<project-path>/Reports``.

******************
Adding New Reports
******************
Here's how to create a new report in PyDSS.

#. Create a new class in a Python file in ``pydss/reports``. The class must
   inherit from ``ReportBase``.
#. Implement the required methods:

   - ``generate``:  Generates the report files. This should create the files in
     ``<project-path>/Reports``.
   - ``get_required_exports``:  Defines the export parameters at runtime. Refer
     to :ref:`tutorial:Pre-filtering Export Data`.

********
Examples
********
Refer to the simulation settings in ``tests/data/pv_reports_project/simulation.toml``
for an example configuration that enables these reports.
