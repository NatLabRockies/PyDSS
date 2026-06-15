*****************
Gen Controller
*****************

Controller Overview
-------------------
The Gen Controller implements smart inverter control modes for OpenDSS Generator objects.
It provides Volt-Var (VVar) control using a heavy-ball damping algorithm to regulate reactive
power output based on the voltage at the point of common coupling (PCC).

This controller is conceptually similar to the :doc:`PvController` but operates on Generator
elements instead of PVSystem elements. It is useful for modeling inverter-based distributed
generators with grid-support functions.

Controller Model
----------------

.. py:class:: pydss.pyControllers.Controllers.GenController.GenController

The controller is configured with the following TOML settings:

.. list-table:: GenController Settings
   :header-rows: 1
   :widths: 30 15 55

   * - Parameter
     - Type
     - Description
   * - ``Control1``
     - string
     - First control mode (``"None"`` or ``"VVar"``)
   * - ``Control2``
     - string
     - Second control mode
   * - ``Control3``
     - string
     - Third control mode
   * - ``Priority``
     - string
     - Control priority (``"Var"`` or ``"Watt"``)
   * - ``DampCoef``
     - float
     - Damping coefficient for heavy-ball algorithm
   * - ``PFlim``
     - float
     - Power factor limit
   * - ``uMin``
     - float
     - Minimum voltage threshold for Volt-Var curve (p.u.)
   * - ``uMax``
     - float
     - Maximum voltage threshold for Volt-Var curve (p.u.)
   * - ``uDbMin``
     - float
     - Lower deadband voltage (p.u.)
   * - ``uDbMax``
     - float
     - Upper deadband voltage (p.u.)
   * - ``Model as PVsystem``
     - bool
     - If true, models the generator with PVSystem-like behavior

Usage Example
-------------

.. code-block:: toml

   ["Generator.gen1"]
   Control1 = "VVar"
   Control2 = "None"
   Control3 = "None"
   Priority = "Var"
   DampCoef = 0.8
   PFlim = 0.9
   uMin = 0.92
   uMax = 1.08
   uDbMin = 0.98
   uDbMax = 1.02
   Model as PVsystem = false
