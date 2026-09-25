******************************
PV System Voltage Ride-Through
******************************

Controller overview
-------------------

This controller implements the voltage ride-through requirements from both IEEE 1547-2003 and the IEEE 1547-2018 standard.

The controller implements ride-through requirements in complete detail. This includes

- Implementation of inverter behavior in defined regions such as may-trip, current-limited, and permissive operation.
- Implementation of inverter categories for the IEEE 1547-2018 standard.
- System behavior under multiple disturbances.
- System recovery under momentary cessation and trip scenarios.

.. image:: PvVoltageRideThru3.png
  :width: 400
  :alt: Alternative text

The figure above shows the inverter response to a fault. The inverter is configured for momentary
cessation in the may-trip region. It enters the momentary-cessation region (gray), and the PV
system is temporarily disconnected. Once the fault is cleared, the PV system returns to full power
in a 0.4-second ramp, consistent with IEEE 1547-2018.

.. image:: PvVoltageRideThru2.png
  :width: 400
  :alt: Alternative text

The figure above shows the inverter response to multiple faults. The inverter is configured to trip
after multiple faults. Under the modeled standard, it trips on the second consecutive fault. After
the first fault, the PV system enters momentary cessation and begins to recover. After the second
fault, it trips and must wait at least 300 seconds before reconnecting.

.. image:: PvVoltageRideThru1.png
  :width: 400
  :alt: Alternative text

The figure above shows the inverter response to multiple faults when tripping is disabled. With
each fault, the PV system enters momentary cessation and begins a ramped recovery. It recovers
fully after the third fault.


Controller model
----------------

.. autopydantic_model:: pydss.py_controllers.models.PvVoltageRideThruModel

Controller options
------------------

.. autoenum:: pydss.py_controllers.enumerations.PvStandard

.. autoenum:: pydss.py_controllers.enumerations.VoltageCalcModes

.. autoenum:: pydss.py_controllers.enumerations.RideThroughCategory

.. autoenum:: pydss.py_controllers.enumerations.PermissiveOperation

.. autoenum:: pydss.py_controllers.enumerations.MayTripOperation

.. autoenum:: pydss.py_controllers.enumerations.MultipleDisturbances

.. autoenum:: pydss.py_controllers.enumerations.CategoryI

.. autoenum:: pydss.py_controllers.enumerations.CategoryII

.. autoenum:: pydss.py_controllers.enumerations.CategoryIII

Usage example
-------------
    see test_controllers.py in the tests folder
