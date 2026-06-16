*****************
PV Dynamic
*****************

Controller Overview
-------------------
The PV Dynamic controller provides a detailed dynamic simulation model for PV inverter systems
using the `PVDER <https://github.com/tdcosim/SolarPV-DER-simulation-utility>`_ (Photovoltaic
Distributed Energy Resource) package. Unlike the quasi-static models used by other PyDSS
controllers, this controller simulates sub-cycle inverter dynamics including:

- Maximum Power Point Tracking (MPPT)
- Grid-connected inverter current control (GCC)
- DC bus voltage regulation
- Reactive power control
- Low/High Voltage Ride-Through (LVRT/HVRT)
- Low Frequency Ride-Through (LFRT)

This controller is intended for dynamic simulations (sub-second time steps) and requires the
``pvder`` package to be installed.

Controller Model
----------------

.. py:class:: pydss.pyControllers.Controllers.PvDynamic.PvDynamic

The controller accepts an extensive set of parameters organized into categories:

**Power Ratings**

.. list-table::
   :header-rows: 1
   :widths: 35 15 50

   * - Parameter
     - Type
     - Description
   * - ``RATED_POWER_AC_VA``
     - float
     - Rated AC power output (VA)
   * - ``RATED_POWER_DC_WATTS``
     - float
     - Rated DC power input (W)
   * - ``STEADY_STATE``
     - bool
     - Initialize in steady-state mode

**PV Module Parameters**

.. list-table::
   :header-rows: 1
   :widths: 35 15 50

   * - Parameter
     - Type
     - Description
   * - ``Np``
     - int
     - Number of parallel strings
   * - ``Ns``
     - int
     - Number of series modules
   * - ``Vdcmpp0``
     - float
     - Initial MPP DC voltage (V)
   * - ``Vdcmpp_max``
     - float
     - Maximum MPP DC voltage (V)
   * - ``Vdcmpp_min``
     - float
     - Minimum MPP DC voltage (V)

**Inverter Ratings**

.. list-table::
   :header-rows: 1
   :widths: 35 15 50

   * - Parameter
     - Type
     - Description
   * - ``Vdcrated``
     - float
     - Rated DC bus voltage (V)
   * - ``Ioverload``
     - float
     - Overload current limit (p.u.)
   * - ``Vrmsrated``
     - float
     - Rated RMS voltage (V)

**Feature Flags**

.. list-table::
   :header-rows: 1
   :widths: 35 15 50

   * - Parameter
     - Type
     - Description
   * - ``MPPT_ENABLE``
     - bool
     - Enable Maximum Power Point Tracking
   * - ``VOLT_VAR_ENABLE``
     - bool
     - Enable Volt-Var control
   * - ``LVRT_ENABLE``
     - bool
     - Enable Low Voltage Ride-Through
   * - ``HVRT_ENABLE``
     - bool
     - Enable High Voltage Ride-Through
   * - ``LFRT_ENABLE``
     - bool
     - Enable Low Frequency Ride-Through

Usage Example
-------------

.. code-block:: toml

   ["PVSystem.pv1"]
   STEADY_STATE = true
   RATED_POWER_AC_VA = 50000
   RATED_POWER_DC_WATTS = 52500
   DER_ID = "pv1"
   Np = 11
   Ns = 735
   Vdcmpp0 = 750.0
   Vdcrated = 550.0
   MPPT_ENABLE = true
   VOLT_VAR_ENABLE = false
   LVRT_ENABLE = true
   HVRT_ENABLE = true
