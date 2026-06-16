********************
Thermostatic Load
********************

Controller Overview
-------------------
The Thermostatic Load controller models temperature-dependent loads such as HVAC systems,
water heaters, and refrigeration units. It simulates a first-order thermal model where the
load cycles on and off to maintain temperature within a deadband defined by minimum and
maximum temperature setpoints.

The thermal dynamics follow:

.. math::

   \frac{dT}{dt} = -\frac{1}{RC}(T - T_a) + \frac{\mu \cdot P}{C}

where:

- :math:`T` is the current temperature
- :math:`T_a` is the ambient temperature
- :math:`R` is the thermal resistance
- :math:`C` is the thermal capacitance
- :math:`P` is the electrical power consumption
- :math:`\mu` is a scaling factor

When the temperature reaches ``Tmax``, the load turns on (cooling). When it drops to
``Tmin``, the load turns off. This creates a natural duty cycling behavior.

Controller Model
----------------

.. py:class:: pydss.pyControllers.Controllers.ThermostaticLoad.ThermostaticLoad

.. list-table:: ThermostaticLoad Settings
   :header-rows: 1
   :widths: 25 15 60

   * - Parameter
     - Type
     - Description
   * - ``Tmax``
     - float
     - Maximum temperature setpoint (load turns on)
   * - ``Tmin``
     - float
     - Minimum temperature setpoint (load turns off)
   * - ``kw``
     - float
     - Rated power consumption of the load (kW)
   * - ``R``
     - float
     - Thermal resistance of the enclosure
   * - ``C``
     - float
     - Thermal capacitance of the enclosure
   * - ``mu``
     - float
     - Ambient/comfort scaling factor

Usage Example
-------------

.. code-block:: toml

   ["Load.hvac1"]
   Tmax = 24.0
   Tmin = 20.0
   kw = 3.5
   R = 2.0
   C = 1.5
   mu = 1.0
