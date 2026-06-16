.. pydss documentation master file

#####
PyDSS
#####

***********
About PyDSS
***********

PyDSS is a Python wrapper for `OpenDSS <https://www.epri.com/pages/sa/opendss>`_ that extends its
organizational, analytical, and co-simulation capabilities. It is built on top of
`OpenDSSDirect.py <https://pypi.org/project/OpenDSSDirect.py/>`_.

Key Features
============

- **Custom Control Algorithms** — Define Python-based controllers for any circuit element, executed
  at each simulation time step. 13 built-in controllers are included.
- **HELICS Co-simulation** — Integrate with external simulators via the
  `HELICS <https://github.com/GMLC-TDC/HELICS>`_ framework for cyber-physical co-simulation studies.
- **Scenario Management** — Run multiple scenarios on a shared OpenDSS model with independent
  controllers, exports, and post-processing.
- **Flexible Data Export** — Export results to HDF5 or CSV with per-element filtering, regex-based
  selection, moving averages, and group aggregation.
- **Automated Reports** — Generate reports for voltage metrics, thermal metrics, PV
  clipping/curtailment, capacitor switching, tap changes, and feeder losses.
- **Monte Carlo Studies** — Built-in support for Monte Carlo simulations with profile management.
- **Extension Architecture** — Plugin system for custom controllers, post-processing scripts, and
  report types.

.. _installation_label:

************
Installation
************

Recommendation: Install PyDSS in a conda virtual environment.

.. code-block:: bash

    $ conda create -n pydss python=3.11
    $ conda activate pydss

Install the latest release from PyPI:

.. code-block:: bash

    $ pip install NREL-pydss

Or install from source for development:

.. code-block:: bash

    $ git clone https://github.com/NatLabRockies/PyDSS
    $ cd PyDSS
    $ pip install -e ".[dev]"

Verify the installation:

.. code-block:: bash

    $ pydss --help

.. note::

   PyDSS requires Python 3.9 or later. Python 3.11 is recommended.


*************
Running PyDSS
*************

Refer to the :ref:`quick_start_label` for basic instructions on how to configure PyDSS to run a
simulation with an existing OpenDSS model.

Refer to :ref:`tutorial_label` for in-depth instructions on customizing a PyDSS project, including
data export options, controllers, and programmatic result access.


************************
Additional Documentation
************************

.. toctree::
   :maxdepth: 1

   quickstart
   tutorial
   project_layout
   interfaces
   co-simulation_support
   controllers_overview
   reports
   hdf-data-format

License
=======

BSD 3-Clause License. Copyright (c) 2018, Alliance for Sustainable Energy LLC. All rights reserved.

See the `LICENSE <https://github.com/NatLabRockies/PyDSS/blob/master/LICENSE>`_ file for details.

Contact
=======

Questions? Please send an email to aadil.latif@nrel.gov or aadil.latif@gmail.com
