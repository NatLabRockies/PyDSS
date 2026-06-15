*****************
Socket Controller
*****************

Controller Overview
-------------------
The Socket Controller enables PyDSS to interface with external software via TCP socket
communication. At each simulation time step, it sends element property values to an external
process and receives updated control setpoints in return. This bidirectional exchange allows
integration with controllers implemented in other languages or tools (e.g., Modelica, MATLAB,
hardware-in-the-loop setups).

The controller operates in two priority stages:

- **Priority 0**: Reads specified input properties from the controlled element, packs them as
  binary doubles, and sends them to the external process via socket.
- **Priority 1**: Receives new setpoint values from the external process and applies them to
  the controlled element's output properties.

For detailed co-simulation usage, see :doc:`../Co-simulation Interfaces`.

Controller Model
----------------

.. py:class:: pydss.pyControllers.Controllers.SocketController.SocketController

.. list-table:: SocketController Settings
   :header-rows: 1
   :widths: 25 15 60

   * - Parameter
     - Type
     - Description
   * - ``IP``
     - string
     - IP address of the socket server (e.g., ``"127.0.0.1"``)
   * - ``Port``
     - int
     - Port number for the socket connection
   * - ``Encoding``
     - bool
     - Whether to use text encoding (typically ``false`` for binary)
   * - ``Buffer``
     - int
     - Buffer size in bytes for socket communication
   * - ``Index``
     - string
     - Comma-separated index selectors for input values (e.g., ``"Even,Even"``)
   * - ``Inputs``
     - string
     - Comma-separated element properties to read and send (e.g., ``"VoltagesMagAng,Powers"``)
   * - ``Outputs``
     - string
     - Comma-separated element properties to update from received data (e.g., ``"kW"``)

Usage Example
-------------

.. code-block:: toml

   ["Load.mpx000635970"]
   IP = "127.0.0.1"
   Port = 5001
   Encoding = false
   Buffer = 1024
   Index = "Even,Even"
   Inputs = "VoltagesMagAng,Powers"
   Outputs = "kW"
