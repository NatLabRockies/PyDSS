**********************
Transformer Controller
**********************

Controller Overview
-------------------
The Transformer Controller monitors power flow through a transformer or voltage regulator and
locks the tap changer when reverse power flow is detected. This prevents undesirable tap
operations that can occur when distributed generation causes power to flow upstream through
a load tap changer (LTC) or voltage regulator.

When reverse power flow is detected, the controller disables the RegControl associated with
the transformer, effectively locking the tap position. When forward power flow resumes,
the controller re-enables the RegControl to allow normal voltage regulation.

Controller Model
----------------

.. py:class:: pydss.pyControllers.Controllers.xfmrController.xfmrController

.. list-table:: xfmrController Settings
   :header-rows: 1
   :widths: 25 15 60

   * - Parameter
     - Type
     - Description
   * - ``RPF locking``
     - bool
     - Enable reverse power flow locking (``true`` to activate)

Usage Example
-------------

.. code-block:: toml

   ["Transformer.xfmr1"]
   RPF locking = true
