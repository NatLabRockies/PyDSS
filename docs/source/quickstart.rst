.. _quick_start_label:

*****************
Quick Start Guide
*****************

This page provides a short guide to get PyDSS up and running. If you have not already installed
PyDSS, please follow the instructions at :ref:`installation_label`.

The basic steps are:

1. Create an empty project
2. Copy your OpenDSS model files into the project
3. Customize the simulation settings
4. Run the simulation

Create an empty project
=======================
PyDSS requires a specific directory structure with configuration files that specify how to run a
simulation. Run this command to create an empty project:

.. code-block:: bash

    $ pydss create-project --project=my-project --scenarios="scenario1,scenario2" --path=./pydss-projects

This creates the directory structure described in :ref:`pydss_project_layout`.

OpenDSS Models
==============

1. Copy your OpenDSS model files into ``./pydss-projects/my-project/DSSfiles/``.
2. Set the field ``dss_file`` in ``simulation.toml`` to the OpenDSS entry point filename
   (e.g., ``Master.dss``).

Customize the simulation settings
=================================
The file ``./pydss-projects/my-project/simulation.toml`` is the main configuration file for the
project. Key settings include:

- **Simulation type**: QSTS (quasi-static time series), Dynamic, Snapshot, or Monte Carlo
- **Start time and duration**: When the simulation starts and how long it runs
- **Step resolution**: Time step size (in seconds)
- **Export options**: What data to collect and in what format (HDF5 or CSV)

Refer to :ref:`SimulationSettingsModel` for the full list of settings.

Each scenario has its own config files for additional customization:

- ``ExportLists/`` — What data to export
- ``pyControllerList/`` — Controller configurations

Run the simulation
==================

.. code-block:: bash

   $ pydss run ./pydss-projects/my-project

Results
=======
- **Exported data**: ``./pydss-projects/my-project/Exports/<scenario-name>/``
- **Reports**: ``./pydss-projects/my-project/Reports/``
- **HDF5 store**: ``./pydss-projects/my-project/store.h5``

Access results programmatically using the Python API:

.. code-block:: python

    from pydss.pydss_results import PyDssResults

    results = PyDssResults("./pydss-projects/my-project")
    scenario = results.scenarios[0]
    df = scenario.get_dataframe("Buses", "puVmagAngle", "bus_name")

Refer to the :ref:`tutorial_label` for more detailed examples.
