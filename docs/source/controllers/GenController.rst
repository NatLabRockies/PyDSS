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

.. py:class:: pydss.py_controllers.controllers.gen_controller.GenController

The controller reads component-specific settings from its TOML section. The primary settings are
listed below using the current configuration names:

.. list-table:: GenController Settings
   :header-rows: 1
   :widths: 30 15 55

   * - Parameter
     - Type
     - Description
   * - ``damp_coef``
     - float
     - Damping coefficient for heavy-ball algorithm
   * - ``q_limit``
     - float
     - Reactive power limit
   * - ``u_min``
     - float
     - Minimum voltage threshold for Volt-Var curve (p.u.)
   * - ``u_max``
     - float
     - Maximum voltage threshold for Volt-Var curve (p.u.)
   * - ``u_db_min``
     - float
     - Lower deadband voltage (p.u.)
   * - ``u_db_max``
     - float
     - Upper deadband voltage (p.u.)

Usage Example
-------------

.. code-block:: toml

   ["Generator.gen1"]
  damp_coef = 0.8
  q_limit = 1.0
  u_min = 0.92
  u_max = 1.08
  u_db_min = 0.98
  u_db_max = 1.02
