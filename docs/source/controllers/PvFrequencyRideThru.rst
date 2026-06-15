**************************
PV Frequency Ride-Through
**************************

Controller Overview
-------------------
The PV Frequency Ride-Through controller implements frequency ride-through behavior per
IEEE 1547-2003 and IEEE 1547-2018 standards for PVSystem and Generator elements. It monitors
the system frequency and determines whether the inverter should continue operating, trip
offline, or reconnect based on configurable frequency thresholds and clearing times.

The controller defines over-frequency (OF) and under-frequency (UF) protection regions using
Shapely geometric polygons. When the operating point (frequency, duration) enters a trip
region, the inverter is disconnected. After the fault clears, the inverter reconnects
following a configurable dead time and power ramp.

This controller supports three ride-through categories (I, II, III) with different
frequency thresholds per the IEEE 1547-2018 standard.

Controller Model
----------------

.. py:class:: pydss.pyControllers.Controllers.PvFrequencyRideThru.PvFrequencyRideThru

.. list-table:: PvFrequencyRideThru Settings
   :header-rows: 1
   :widths: 35 15 50

   * - Parameter
     - Type
     - Description
   * - ``OF1 - Hz``
     - float
     - Over-frequency level 1 threshold (Hz)
   * - ``OF1 CT - sec``
     - float
     - Over-frequency level 1 clearing time (seconds)
   * - ``OF2 - Hz``
     - float
     - Over-frequency level 2 threshold (Hz)
   * - ``OF2 CT - sec``
     - float
     - Over-frequency level 2 clearing time (seconds)
   * - ``UF1 - Hz``
     - float
     - Under-frequency level 1 threshold (Hz)
   * - ``UF1 CT - sec``
     - float
     - Under-frequency level 1 clearing time (seconds)
   * - ``UF2 - Hz``
     - float
     - Under-frequency level 2 threshold (Hz)
   * - ``UF2 CT - sec``
     - float
     - Under-frequency level 2 clearing time (seconds)
   * - ``Ride-through Category``
     - string
     - IEEE 1547-2018 category (``"Category I"``, ``"Category II"``, or ``"Category III"``)
   * - ``Reconnect deadtime - sec``
     - float
     - Minimum time between trip and reconnection (seconds)
   * - ``Reconnect Pmax time - sec``
     - float
     - Time to ramp back to maximum power after reconnection (seconds)
   * - ``Priority``
     - string
     - Control priority (``"Var"`` or ``"Watt"``)
   * - ``UcalcMode``
     - string
     - Voltage calculation mode (``"MAX"``, ``"AVG"``, ``"MIN"``, ``"A"``, ``"B"``, ``"C"``)

Usage Example
-------------

.. code-block:: toml

   ["PVSystem.pv1"]
   kVA = 100
   maxKW = 100
   KvarLimit = 44
   OF1 - Hz = 61.2
   OF1 CT - sec = 300
   OF2 - Hz = 62.0
   OF2 CT - sec = 0.16
   UF1 - Hz = 58.5
   UF1 CT - sec = 300
   UF2 - Hz = 56.5
   UF2 CT - sec = 0.16
   Ride-through Category = "Category III"
   Reconnect deadtime - sec = 300
   Reconnect Pmax time - sec = 300
   Priority = "Var"
   UcalcMode = "AVG"
