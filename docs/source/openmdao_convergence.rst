*************************
OpenMDAO Controller Solve
*************************

PyDSS uses OpenMDAO to solve the feedback loop between Python controllers and the OpenDSS
circuit. This is the controller execution model for every simulation time point that has configured
controllers.

Architecture
============

The simulation driver owns time advancement and result export. OpenMDAO owns the nonlinear solve:

.. code-block:: text

   PyDSS outer loop
       |  apply profiles, external inputs, and the current time
       v
   OpenMDAO Problem
       |-- ControllerExplicitComponent  ->  controller commands
       |-- CircuitExplicitComponent     ->  OpenDSS solve and measurements
       `-- NonlinearBlockGS             ->  coupled convergence
       v
   commit accepted controller state, export results, advance OpenDSS time

During a nonlinear iteration, a controller reads only its declared OpenMDAO inputs and writes only
its declared outputs. The circuit component applies the command batch, solves OpenDSS once, and
returns the measurements needed by the controllers. The solver repeats this cycle until the
residual is within tolerance or the iteration limit is reached.

Configuration
=============

The project settings below configure the OpenMDAO solve:

``Max Control Iterations``
    Maximum number of nonlinear solver iterations permitted at one simulation time point.

``Error tolerance``
    Absolute and relative nonlinear solver tolerance passed to OpenMDAO.

``OpenMDAO Reports``
    Enables OpenMDAO reports and nonlinear solver recording for a direct example or project run.
    Reports are written under the project ``OpenMDAOReports/`` directory.

``Max error tolerance`` and ``Convergence error percent threshold``
    Simulation-level failure policies for convergence errors. These remain outside the OpenMDAO
    model and determine whether repeated failed time points stop the simulation.

A controller configuration uses the settings supported by its component. See the individual
controller pages for the available settings and examples.

Time-step lifecycle
===================

Each outer time point follows this order:

#. PyDSS applies profiles, HELICS values, or other external updates.
#. PyDSS supplies the current simulation time to the circuit component.
#. OpenMDAO resets transient component state and runs the coupled nonlinear model.
#. A converged solve commits controller and circuit state exactly once.
#. PyDSS exports results and advances OpenDSS time.

Trial evaluations during nonlinear convergence must not advance time or commit state. If OpenMDAO
exhausts its iteration limit, the time point is marked unconverged and the configured PyDSS
convergence policy is applied. OpenDSS backend failures are reported separately from OpenMDAO
nonlinear failures.

Reports and failure handling
============================

Set ``OpenMDAO Reports`` to ``true`` when OpenMDAO solver reports are needed for a run. Reports are
written under the project's ``OpenMDAOReports/`` directory. A failed nonlinear solve is reported
to PyDSS and handled according to the project's convergence settings; controller state is not
committed as an accepted time step.
