********************
Storage Controller
********************

Controller Overview
-------------------
The Storage Controller provides multiple control implementations for battery energy storage
systems, supporting both behind-the-meter and front-of-meter applications. Dispatch behavior is
selected through component-specific settings.

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

.. py:class:: pydss.py_controllers.controllers.storage_controller.StorageController

The component accepts ``control`` or ``mode`` for dispatch selection. Other settings depend on the
selected mode. For example, scheduled dispatch uses ``schedule`` and ``schedule_period_sec``;
peak shaving uses ``ps_ub`` and ``damp_coef``.

Usage Example
-------------

**Scheduled dispatch:**

.. code-block:: toml

   ["Storage.batt1"]
  control = "scheduled"
  schedule = [0.0, 25.0, 50.0]
  schedule_period_sec = 3600.0

**Peak Shaving control:**

.. code-block:: toml

   ["Storage.batt1"]
  control = "peak_shaving"
  ps_ub = 50.0
  damp_coef = 0.8
