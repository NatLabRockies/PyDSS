import openmdao.api as om
import pytest
import numpy as np

from pydss.py_controllers.controllers.dynamic_voltage_support import DynamicVoltageSupport
from pydss.py_controllers.controllers.motor_stall_simple import MotorStallSimple
from pydss.py_controllers.controllers.pv_voltage_ride_thru import PvVoltageRideThru
from pydss.py_controllers.controllers.fault_controller import FaultController
from pydss.py_controllers.controllers.gen_controller import GenController
from pydss.py_controllers.controllers.motor_stall import MotorStall
from pydss.py_controllers.controllers.motor_stall_backup import MotorStallBackup
from pydss.py_controllers.controllers.pv_controller import PvController
from pydss.py_controllers.controllers.pv_dynamic import PvDynamic
from pydss.py_controllers.controllers.pv_frequency_ride_thru import PvFrequencyRideThru
from pydss.py_controllers.controllers.socket_controller import SocketController
from pydss.py_controllers.controllers.storage_controller import StorageController
from pydss.py_controllers.controllers.thermostatic_load import ThermostaticLoad
from pydss.py_controllers.controllers.xfmr_controller import XfmrController
from pydss.py_controllers.models import PvControllerModel
from pydss.py_controllers.py_controller import ControllerTypes, Create


def test_all_registered_controllers_are_openmdao_components():
    group = om.Group()
    controllers = []
    for index, controller_type in enumerate(ControllerTypes):
        controller = Create(controller_type, {}, element_name=f"element_{index}")
        group.add_subsystem(f"controller_{index}", controller)
        controllers.append(controller)

    problem = om.Problem(model=group, reports=False)
    problem.setup()
    problem.run_model()
    assert set(problem.model.controller_0._var_rel_names["input"]) >= {
        "measurement_voltage_pu",
        "measurement_active_power",
        "measurement_reactive_power",
        "time_seconds",
    }
    assert set(problem.model.controller_0._var_rel_names["output"]) >= {
        "command_active_power",
        "command_reactive_power",
        "command_enabled",
        "diagnostic_residual",
    }
    for controller in controllers:
        controller.commit_step()
        assert controller.step_count == 1


def test_legacy_controller_settings_are_rejected():
    with pytest.raises(ValueError, match="Legacy controller settings"):
        PvControllerModel(Control1="VVar")


def test_legacy_controller_disable_setting_is_rejected():
    from pydss.simulation_input_models import ProjectModel

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        ProjectModel(**{"Disable pydss controllers": False})


def _controller_runner(controller):
    group = om.Group()
    group.add_subsystem("controller", controller)
    problem = om.Problem(model=group, reports=False)
    problem.setup()

    def run(voltage, active, reactive, time):
        problem.set_val("controller.measurement_voltage_pu", voltage)
        problem.set_val("controller.measurement_active_power", active)
        problem.set_val("controller.measurement_reactive_power", reactive)
        problem.set_val("controller.time_seconds", time)
        problem.run_model()
        values = {
            name: float(np.asarray(problem.get_val(f"controller.{name}")).reshape(-1)[0])
            for name in ("command_active_power", "command_reactive_power", "command_enabled")
        }
        controller.commit_step()
        return values

    return run


def test_pv_voltage_ride_through_trips_and_reconnects():
    controller = PvVoltageRideThru(
        settings={
            "uv_2_pu": 0.5,
            "uv_2_ct_sec": 1.0,
            "reconnect_deadtime_sec": 2.0,
        }
    )
    run = _controller_runner(controller)
    assert run(0.4, 5.0, 1.0, 0.0)["command_enabled"] == 1.0
    assert run(0.4, 5.0, 1.0, 1.1)["command_enabled"] == 0.0
    assert run(1.0, 5.0, 1.0, 2.0)["command_enabled"] == 0.0
    assert run(1.0, 5.0, 1.0, 4.0)["command_enabled"] == 1.0


def test_motor_stall_simple_multiplies_then_disconnects_and_reconnects():
    controller = MotorStallSimple(
        settings={
            "v_stall": 0.6,
            "p_fault": 3.0,
            "q_fault": 4.0,
            "t_protection": 1.0,
            "t_reconnect": 6.0,
        }
    )
    run = _controller_runner(controller)
    stalled = run(0.5, 2.0, 1.0, 0.0)
    assert stalled["command_active_power"] == pytest.approx(6.0)
    assert stalled["command_reactive_power"] == pytest.approx(4.0)
    assert run(0.5, 2.0, 1.0, 1.1)["command_enabled"] == 0.0
    assert run(1.0, 2.0, 1.0, 8.0)["command_enabled"] == 1.0


def test_dynamic_voltage_support_injects_or_absorbs_reactive_power():
    settings = {
        "Trv": 0.001,
        "Tinv": 0.001,
        "dbd1": -0.1,
        "dbd2": 0.1,
        "Kqv": 10.0,
        "kvar_max": 1.0,
        "kvar_min": -1.0,
        "kva": 10.0,
    }
    controller = DynamicVoltageSupport(settings=settings)
    run = _controller_runner(controller)
    assert run(0.8, 2.0, 0.0, 0.0)["command_reactive_power"] > 0.0
    assert run(1.2, 2.0, 0.0, 1.0)["command_reactive_power"] < 0.0


def _run_declared_inputs(controller, values):
    group = om.Group()
    group.add_subsystem("controller", controller)
    problem = om.Problem(model=group, reports=False)
    problem.setup()
    input_names = {name.rsplit(".", 1)[-1] for name in controller._var_rel_names["input"]}
    for name, value in values.items():
        if name in input_names:
            problem.set_val(f"controller.{name}", value)
    problem.run_model()
    result = {
        name: float(np.asarray(problem.get_val(f"controller.{name}")).reshape(-1)[0])
        for name in controller._var_rel_names["output"]
    }
    return result


def test_migrated_time_and_voltage_families_use_synthetic_commands_only():
    fault = FaultController(settings={"start_time_seconds": 2.0, "duration_seconds": 1.0})
    assert _run_declared_inputs(fault, {"time_seconds": 2.5})["command_enabled"] == 1.0
    fault.commit_step()
    assert fault.step_count == 1

    generator = GenController(
        settings={"u_min": 0.9, "u_db_min": 0.95, "u_db_max": 1.05, "u_max": 1.1}
    )
    assert (
        _run_declared_inputs(
            generator,
            {
                "measurement_voltage_pu": 0.9,
                "measurement_active_power": 4.0,
                "measurement_reactive_power": 0.0,
            },
        )["command_reactive_power"]
        > 0.0
    )

    pv = PvController(settings={"uMin": 0.94, "uDbMin": 0.97, "uDbMax": 1.03, "uMax": 1.06})
    assert (
        _run_declared_inputs(
            pv,
            {
                "measurement_voltage_pu": 1.1,
                "measurement_active_power": 2.0,
                "measurement_reactive_power": 0.0,
            },
        )["command_reactive_power"]
        < 0.0
    )

    dynamic = PvDynamic(settings={"response_fraction": 0.5})
    first = dynamic.compute_commands(
        {
            "measurement_active_power": 4.0,
            "measurement_reactive_power": 2.0,
            "measurement_voltage_pu": 1.0,
            "time_seconds": 0.0,
        }
    )
    dynamic.commit_step()
    second = dynamic.compute_commands(
        {
            "measurement_active_power": 0.0,
            "measurement_reactive_power": 0.0,
            "measurement_voltage_pu": 1.0,
            "time_seconds": 1.0,
        }
    )
    assert first["command_active_power"] == 4.0
    assert second["command_active_power"] == 2.0


def test_migrated_stall_and_frequency_controllers_commit_state():
    for controller in (
        MotorStall(settings={"v_stall": 0.6, "t_protection": 1.0}),
        MotorStallBackup(settings={"v_stall": 0.6}),
    ):
        result = _run_declared_inputs(
            controller,
            {
                "measurement_voltage_pu": 0.5,
                "measurement_active_power": 2.0,
                "measurement_reactive_power": 1.0,
                "time_seconds": 0.0,
            },
        )
        expected_enabled = 0.0 if isinstance(controller, MotorStallBackup) else 1.0
        assert result["command_enabled"] == expected_enabled
        controller.commit_step()
        assert controller.step_count == 1

    ride_through = PvFrequencyRideThru(
        settings={"f_lower": 59.0, "f_upper": 61.0, "trip_delay_sec": 1.0}
    )
    first = ride_through.compute_commands(
        {
            "measurement_frequency_hz": 58.0,
            "measurement_active_power": 2.0,
            "measurement_reactive_power": 1.0,
            "time_seconds": 0.0,
        }
    )
    assert first["command_enabled"] == 1.0
    ride_through.commit_step()
    second = ride_through.compute_commands(
        {
            "measurement_frequency_hz": 58.0,
            "measurement_active_power": 2.0,
            "measurement_reactive_power": 1.0,
            "time_seconds": 1.1,
        }
    )
    assert second["command_enabled"] == 0.0


def test_migrated_boundary_storage_thermal_and_transformer_controllers():
    socket_controller = SocketController(settings={"active_power": 3.0, "reactive_power": -1.0})
    socket_result = _run_declared_inputs(
        socket_controller, {"measurement_active_power": 0.0, "measurement_reactive_power": 0.0}
    )
    assert socket_result["command_active_power"] == 3.0

    storage = StorageController(settings={"control": "PS", "PS_ub": 5.0, "DampCoef": 1.0})
    assert (
        _run_declared_inputs(
            storage, {"measurement_active_power": 8.0, "measurement_reactive_power": 0.0}
        )["command_active_power"]
        == 5.0
    )

    thermostat = ThermostaticLoad(
        settings={
            "Tmin": 18.0,
            "Tmax": 20.0,
            "kw": 2.0,
            "initial_temperature": 19.0,
            "initial_on": True,
        }
    )
    assert (
        _run_declared_inputs(thermostat, {"time_seconds": 0.0, "measurement_active_power": 2.0})[
            "command_active_power"
        ]
        == 2.0
    )

    transformer = XfmrController(settings={"RPF locking": True})
    assert (
        _run_declared_inputs(transformer, {"measurement_active_power": -1.0})["command_enabled"]
        == 0.0
    )
