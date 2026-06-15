********************
Storage Controller
********************

Controller Overview
-------------------
The Storage Controller provides multiple control implementations for battery energy storage
systems, supporting both behind-the-meter and front-of-meter applications. It supports up to
three cascading control modes that can be combined for complex dispatch strategies.

Available control modes:

- **None** — No active control
- **PS** — Peak Shaving: reduces peak demand by discharging storage
- **CF** — Capacity Firming: smooths output variability
- **TT** — Time Triggered: charge/discharge at scheduled times
- **RT** — Real Time: real-time dispatch control
- **SH** — Scheduled: follows a pre-defined schedule
- **NETT** — Non-Export Time Triggered: prevents reverse power flow
- **TOU** — Time of Use: optimizes charge/discharge based on tariff structure
- **DemChg** — Demand Charge: manages demand charges
- **CPF** — Constant Power Factor
- **VPF** — Variable Power Factor
- **VVar** — Volt-Var reactive power control

Controller Model
----------------

.. py:class:: pydss.pyControllers.Controllers.StorageController.StorageController

.. list-table:: StorageController Settings
   :header-rows: 1
   :widths: 30 15 55

   * - Parameter
     - Type
     - Description
   * - ``Control1``
     - string
     - Primary control mode (see modes listed above)
   * - ``Control2``
     - string
     - Secondary control mode
   * - ``Control3``
     - string
     - Tertiary control mode
   * - ``alpha``
     - float
     - Smoothing coefficient for control response
   * - ``beta``
     - float
     - Damping coefficient for control response
   * - ``DampCoef``
     - float
     - General damping coefficient
   * - ``touLoadLim``
     - float
     - Load limit for Time of Use control (kW)
   * - ``%touCharge``
     - float
     - Charge rate during TOU off-peak periods (%)
   * - ``touTarrifStructure``
     - list
     - TOU tariff schedule definition
   * - ``PowerMeaElem``
     - string
     - Element used for power measurement in TOU mode
   * - ``DemandChgThreh[kWh]``
     - float
     - Demand charge threshold (kWh)

Usage Example
-------------

**Time of Use control:**

.. code-block:: toml

   ["Storage.batt1"]
   Control1 = "TOU"
   Control2 = "None"
   Control3 = "None"
   alpha = 0.1
   beta = 0.1
   DampCoef = 0.5
   touLoadLim = 50
   %touCharge = 100

**Peak Shaving control:**

.. code-block:: toml

   ["Storage.batt1"]
   Control1 = "PS"
   Control2 = "None"
   Control3 = "None"
   alpha = 0.1
   beta = 0.1
   DampCoef = 0.8
