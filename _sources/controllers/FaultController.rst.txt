*****************
Fault Controller
*****************

Controller Overview
-------------------
The Fault Controller induces faults on a bus for dynamic simulation studies. It creates an
OpenDSS Fault object between two buses and enables/disables it based on configurable timing
parameters. This is useful for studying system response to short-circuit events, voltage
sags, and fault ride-through behavior of DERs.

The controller operates in a simple time-based fashion: the fault is activated at a specified
start time and cleared after a specified duration.

Controller Model
----------------

.. py:class:: pydss.pyControllers.Controllers.FaultController.FaultController

The controller is configured with the following TOML settings:

.. list-table:: FaultController Settings
   :header-rows: 1
   :widths: 30 15 55

   * - Parameter
     - Type
     - Description
   * - ``Bus1``
     - string
     - Primary bus for the fault connection
   * - ``Bus2``
     - string
     - Secondary bus for the fault connection
   * - ``Fault resistance``
     - float
     - Resistance of the fault (ohms)
   * - ``Fault start time (sec)``
     - float
     - Simulation time at which the fault is energized (seconds)
   * - ``Fault duration (sec)``
     - float
     - Duration the fault remains active (seconds)

Usage Example
-------------

.. code-block:: toml

   ["Bus.fault_bus"]
   Bus1 = "bus1"
   Bus2 = "bus2"
   Fault resistance = 0.0001
   Fault start time (sec) = 0.3
   Fault duration (sec) = 0.5
