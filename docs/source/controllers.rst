###########
Controllers
###########

PyDSS includes 14 built-in OpenMDAO controller components for common distribution system
elements. Each controller is configured via TOML files in a scenario's
``pyControllerList/`` directory and connected to the OpenDSS circuit through declared
measurements and commands.

Controller calculations are evaluated by OpenMDAO's nonlinear solver. A controller does not call
OpenDSS directly, advance simulation time, or run its own iteration loop. State is committed only
after the coupled circuit/controller solve converges.

Configuration is component-specific. Use the settings documented on each controller page; control
behavior is no longer assembled from numbered control slots.

For detailed documentation on each controller, see :doc:`controllers_overview`.

.. toctree::
   :maxdepth: 2

   controllers_overview

