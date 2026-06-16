.. _pydss_project_layout:

********************
PyDSS Project Layout
********************
A PyDSS project is made up of one or more scenarios that run simulations on a shared OpenDSS
model. Scenarios allow users to customize inputs, outputs, and controls independently.
Use cases for multiple scenarios include:

- Running different control algorithms on the same circuit
- Running snapshot simulations at different time points
- Exporting different sets of data
- Running custom post-process scripts after simulation

Project Structure
=================

::

    my-project/
    ├── simulation.toml              # Main simulation configuration
    ├── store.h5                     # HDF5 data store (created after run)
    ├── DSSfiles/                    # OpenDSS model files
    │   ├── Master.dss
    │   └── ...
    ├── Exports/                     # Simulation output (per scenario)
    │   └── <scenario-name>/
    ├── Reports/                     # Generated reports
    ├── Logs/                        # Simulation logs
    ├── Profiles/                    # Load/PV profiles (optional)
    │   ├── profiles.hdf5
    │   └── mapping.toml
    └── Scenarios/
        └── <scenario-name>/
            ├── ExportLists/         # Export configuration
            │   ├── Exports.toml
            │   └── Subscriptions.toml
            ├── pyControllerList/    # Controller configurations
            │   ├── PvController.toml
            │   └── StorageController.toml
            ├── pyPlotList/          # Plot configuration
            ├── PostProcess/         # Post-simulation scripts
            └── Monte_Carlo/         # Monte Carlo settings

Simulation Settings
===================
The main configuration file is ``simulation.toml``, located at the project root.
This file controls all aspects of the simulation including timing, solver settings,
export options, co-simulation, and reports.

Refer to :ref:`SimulationSettingsModel` for the full schema.

Scenarios
=========
Each scenario has its own configuration directory under ``Scenarios/<scenario-name>/``.
The key subdirectories are:

**ExportLists/** — Configures what data to export. The ``Exports.toml`` file defines
which element classes and properties to collect. See :ref:`tutorial:Pre-filtering Export Data`.

**pyControllerList/** — Configures controllers for this scenario. Each ``.toml`` file
maps element names to controller settings. See :ref:`controllers_overview:Controller Documentation`.

**PostProcess/** — Optional Python scripts to run after each simulation solve step.

Exports
=======
When ``export_results`` is enabled, exported data is written to
``Exports/<scenario-name>/``. The format (HDF5 or CSV) is configured in ``simulation.toml``.

Reports
=======
When reports are enabled in ``simulation.toml``, generated report files are written to
``Reports/``. See :doc:`reports` for available report types.

HDF5 Store
==========
All exported data is also stored in ``store.h5`` at the project root. This provides
efficient compressed storage with ~95% compression ratio. See :doc:`hdf-data-format`
for the internal layout.
