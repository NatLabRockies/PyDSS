# PyDSS OpenMDAO Migration Plan

## Current Status

The core migration is implemented and verified. All registered controller types
are OpenMDAO explicit components, nonlinear convergence is owned by OpenMDAO,
and the full test suite passes. The legacy controller-disable setting and
runtime bypass have been removed.

Remaining work is verification depth rather than a second controller runtime:
add dedicated integration coverage for HELICS, socket control, Monte Carlo,
harmonic sweeps, and dry-run behavior, then review performance and numerical
baselines for each supported mode.

## Goal

Replace the PyDSS controller convergence implementation with an OpenMDAO model. The refactor is intentionally breaking: there is no legacy controller API, priority loop, `DSSInstance` convergence management, or compatibility translation for the old controller configuration format.

OpenMDAO will own nonlinear convergence for each simulation time point. OpenDSS remains the circuit solver and model backend, but it is called by an explicit OpenMDAO circuit component.

## Target Architecture

```text
PyDSS time-step orchestration
  -> OpenMDAO Problem / Group
       -> CircuitExplicitComponent
            inputs: controller commands, exogenous updates, time
            compute: apply inputs to OpenDSS, solve once, read measurements
            outputs: voltages, powers, currents, frequency, states
       -> ControllerExplicitComponent instances
            inputs: circuit measurements, time, profiles, controller settings
            compute: calculate commands and residual/error outputs
            outputs: OpenDSS commands and controller diagnostics
       -> OpenMDAO nonlinear solver
            owns iteration, residual evaluation, tolerance, and iteration limit
  -> result export and post-processing
```

The circuit and controller components form an OpenMDAO cycle: controller outputs are connected to circuit inputs, and circuit measurements are connected back to controller inputs. The OpenMDAO nonlinear solver resolves that cycle. Components must not call `reSolve`, run a controller loop, or inspect an iteration priority.

### Component contracts

`CircuitExplicitComponent`

- Owns the OpenDSS instance/adapter and all OpenDSS writes and solve calls.
- Declares stable, namespaced inputs for controller commands and exogenous simulation updates.
- Declares stable, namespaced outputs for every measurement consumed by controllers or exports.
- Calls the appropriate OpenDSS solve exactly as required by one `compute` evaluation.
- Reports OpenDSS convergence as a component diagnostic and raises the configured OpenDSS error when the backend solve fails.
- Exposes a time-step commit/reset operation outside `compute` for stateful simulation progression.

`ControllerExplicitComponent`

- Subclasses `openmdao.api.ExplicitComponent`.
- Implements `initialize`, `setup`, and `compute`; `compute_partials` is optional and initially uses finite difference metadata where derivatives are needed.
- Reads only OpenMDAO inputs and immutable controller configuration during `compute`.
- Writes only OpenMDAO outputs; it does not mutate OpenDSS objects directly.
- Emits command outputs plus a normalized residual/diagnostic output where useful for reporting.
- Uses explicit time-step lifecycle methods for committed state. Nonlinear trial evaluations must not advance time-series state.

`OpenDSSModel`

- Replaces the current `OpenDSS` controller/convergence responsibilities with model construction, time-step execution, and result integration.
- Builds one OpenMDAO `Problem` per active circuit/model context and one reusable `Group` per simulation.
- Configures the selected OpenMDAO nonlinear solver from the project convergence settings.
- Keeps result storage, HELICS exchange, profiles, frequency sweeps, and post-processors outside the nonlinear model unless a signal is required as an explicit component input/output.

## Breaking API and Configuration Changes

1. Add OpenMDAO as a required project dependency.
2. Replace the abstract `Update(Priority, Time, UpdateResults)` contract with OpenMDAO lifecycle methods.
3. Remove `CONTROLLER_PRIORITIES`, `ControllerManager` priority iteration, `_update_controllers`, and controller-local convergence aggregation.
4. Remove `dssSolver` from controller constructors. Controllers receive OpenMDAO inputs instead of a solver or DSS object.
5. Remove direct DSS object access from controller implementations. A narrow measurement/command schema becomes the only controller data contract.
6. Remove all priority fields and enums, including PV watt/var priority behavior. Any resulting command arbitration must be represented explicitly as a controller output rule or circuit command constraint.
7. Replace `Control1`, `Control2`, and `Control3` configuration with an ordered or named control strategy declared by each component. The new schema must not translate old keys.
8. Remove `disable_pydss_controllers`, PyDSS controller iteration settings, and PyDSS controller convergence thresholds from runtime behavior. Retain only settings that configure OpenMDAO nonlinear solving and backend OpenDSS failure policy.
9. Update default controller TOML files, scenario files, registry models, docs, examples, and CLI/config validation together. Old files should fail validation with a clear migration error rather than being silently interpreted.

## Implementation Phases

### Phase 1: Establish the OpenMDAO integration boundary

- Add the dependency and verify the supported OpenMDAO version on Python 3.10+.
- Introduce an OpenDSS adapter with explicit methods for model initialization, applying commands, solving, reading measurements, advancing time, and resetting state.
- Define typed measurement and command schemas with deterministic variable names and units.
- Define the `CircuitExplicitComponent` skeleton and a minimal test circuit.
- Define the OpenMDAO model factory and solver configuration from `ProjectModel`.
- Add tests proving a circuit-only OpenMDAO problem can execute a time point and expose OpenDSS convergence failures.

**Exit criteria:** an OpenMDAO problem can execute one circuit evaluation without any controller code and produces stable, documented variables.

### Phase 2: Replace controller discovery and construction

- Replace `pyController.Create` and constructor injection of DSS globals with a registry of `ExplicitComponent` classes and validated component settings.
- Replace `ControllerAbstract` with the new component base class and shared helpers for variable declarations, units, diagnostics, and committed state.
- Update controller model classes to describe component inputs, outputs, and settings rather than legacy method arguments.
- Make controller registration deterministic and independent of OpenDSS active-class iteration.
- Add model-factory tests for one controller instance, multiple controller instances, missing elements, and invalid settings.

**Exit criteria:** controllers are created as OpenMDAO subsystems and connected by variable names, with no `dssInstance`, `dssSolver`, or priority argument in the construction path.

### Phase 3: Migrate controllers by behavioral family

Migrate each implementation to `setup` and `compute`, moving all DSS interaction to declared variables and the circuit component.

1. `PvController`: constant PF, variable PF, volt/var, volt/watt, and cutoff strategies. Remove priority-based watt/var selection and internal `reSolve` calls.
2. `GenController` and `StorageController`: dispatch, PF, volt/var, scheduled, TOU, demand-charge, and non-export behavior. Represent circuit power and time as inputs; commit energy/state history once per accepted time step.
3. `MotorStall`, `MotorStallBackup`, and `MotorStallSimple`: voltage/current/power measurements to model commands. Decide whether backup behavior remains a separate component or becomes a strategy setting.
4. `PvVoltageRideThru`, `PvFrequencyRideThru`, and `DynamicVoltageSupport`: ride-through state machines with explicit state inputs/outputs and a time-step commit boundary.
5. `ThermostaticLoad` and `xfmrController`: load and regulator command outputs driven by declared measurements.
6. `FaultController`: event/time input to fault command outputs.
7. `SocketController`: external command inputs/outputs represented as an explicit interface component, with socket I/O outside nonlinear trial evaluation.
8. `PvDynamic`: isolate PVDER interaction behind declared inputs/outputs and define derivative behavior for the external dynamic model.

For every controller, preserve intended physical behavior but remove `Update`, priority branching, direct DSS calls, controller-owned solves, and active-class traversal.

**Exit criteria:** every registered controller is an `ExplicitComponent`; no controller source contains a priority parameter, direct OpenDSS solve, or direct mutation of a DSS element.

### Phase 4: Integrate the nonlinear model into simulation modes

- Replace the controller block in `OpenDSS.RunStep` with one OpenMDAO model execution per time step.
- Configure the OpenMDAO nonlinear solver with the selected maximum iterations, absolute/relative tolerance, and print/recording options.
- Map OpenMDAO solver failure to the existing user-facing simulation failure policy, then remove the old PyDSS convergence counters and checks.
- Keep OpenDSS backend convergence separate from OpenMDAO model convergence and report both distinctly.
- Define the accepted-step lifecycle: apply profiles/HELICS inputs, execute the OpenMDAO problem, commit controller state, update exports, then advance OpenDSS time.
- Integrate snapshot, QSTS, dynamic, harmonic sweep, HELICS, Monte Carlo, dry-run, and post-processing paths.

**Exit criteria:** all supported simulation modes execute through OpenMDAO, and no simulation path invokes the old controller manager or priority loop.

### Phase 5: Remove legacy implementation and migrate data

- Delete or replace `controllers.py` legacy manager, `pyControllerAbstract.py` legacy protocol, legacy factory paths, and unused priority enumerations.
- Remove old convergence fields and controller-specific iteration reporting from `dssInstance.py`.
- Migrate all default and test scenario TOML files to the new schema.
- Update registry serialization, scenario creation, CLI editing, docs, examples, and API callers.
- Remove obsolete compatibility code and imports after repository-wide reference checks.

**Exit criteria:** repository search finds no legacy `Update` contract, priority loop, `CONTROLLER_PRIORITIES`, controller `reSolve`, or old controller configuration keys in active code/configuration.

### Phase 6: Verification and performance hardening

- Add isolated component tests using a fake circuit adapter and OpenMDAO problem tests using real OpenDSS fixtures.
- Add convergence tests for coupled controller/circuit cycles, solver iteration limits, tolerances, backend failure, and non-convergence reporting.
- Re-run existing controller scenarios and compare exported physical results against approved baselines.
- Add statefulness tests proving repeated nonlinear trial evaluations do not advance time or double-count energy/history.
- Add integration coverage for HELICS, socket control, dynamic voltage support, ride-through, frequency sweep, and post-processors.
- Profile repeated OpenDSS reads and OpenMDAO evaluations; cache only immutable metadata and measurements that are valid within one evaluation.

**Exit criteria:** focused tests and the full test suite pass, result deltas are reviewed for each controller family, and OpenMDAO iteration diagnostics are available for failed simulations.

## Validation Matrix

| Area | Required validation |
|---|---|
| Circuit component | Inputs are applied once per evaluation; outputs reflect the solved circuit; backend failure is surfaced |
| Controller component | `setup` variables are complete; `compute` is deterministic for identical inputs; no DSS or solver dependency |
| Coupling | OpenMDAO nonlinear solver converges a controller/circuit feedback loop within configured limits |
| Stateful controls | Trial evaluations are side-effect free; accepted time steps commit exactly once |
| Configuration | New schema rejects legacy keys and validates component-specific settings |
| Simulation modes | Snapshot, QSTS, dynamic, harmonic, HELICS, Monte Carlo, and dry-run behavior remains covered |
| Results | HDF5 exports, reports, convergence diagnostics, and `skip_export_on_convergence_error` semantics are verified |
| Regression | Existing controller project fixtures are migrated and compared against approved outputs |

## Design Decisions Required Before Implementation

These are the only decisions that materially change the implementation shape:

1. **OpenDSS instance isolation:** should each OpenMDAO `Problem` own a dedicated OpenDSS engine instance, or should the existing process-global `opendssdirect` engine be retained behind the adapter? Dedicated instances are the safer boundary for repeated problems and future parallel execution; retaining the global engine minimizes initial changes but prevents independent simultaneous models.
2. **OpenMDAO nonlinear solver:** should the default be `NewtonSolver`, `BroydenSolver`, or `NonlinearBlockGS`? The proposed initial default is `NonlinearBlockGS` because the OpenDSS component is a black-box explicit evaluation and finite-difference Jacobians may be expensive or unreliable. A Newton/Broyden option can be exposed after convergence baselines exist.
3. **Derivatives:** should all components initially declare finite-difference partials, or should the first release declare no derivatives and use a solver that does not require them? The proposed default is no analytic derivatives and `NonlinearBlockGS`, with finite-difference metadata added only where a chosen solver requires it.
4. **Controller composition:** should a configured controller with multiple behaviors become one component with a strategy setting, or should each behavior be a separate connected component? The proposed default is one component per configured controlled element, with internal strategy dispatch that remains pure inside `compute`.
5. **OpenMDAO grouping:** should all controller instances share one group per circuit, or should each controller family be placed in a subgroup? The proposed default is one circuit group with family subgroups for naming and diagnostics.
6. **State lifecycle API:** is it acceptable for the simulation driver to call an explicit `commit_step()` method after a successful OpenMDAO solve? This is the proposed approach because mutating state inside `compute` is unsafe under nonlinear trial evaluations.

## Approval Gate

Implementation starts only after this plan and the six decisions above are approved. The first implementation change will be the Phase 1 boundary and its focused circuit-component test; no legacy behavior will be preserved while the migration is underway.