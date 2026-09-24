from collections.abc import Mapping
from typing import Any

from pydss.openmdao_components import ControllerExplicitComponent, VariableSpec


class PvVoltageRideThru(ControllerExplicitComponent):
    """OpenMDAO PV voltage ride-through component."""

    def setup(self) -> None:
        self._state = {
            "connected": True,
            "violation_start": None,
            "reconnect_start": None,
            "last_time": None,
        }
        self._pending_state = None
        self._step_count = 0
        super().setup()

    def input_specs(self) -> tuple[VariableSpec, ...]:
        return (
            VariableSpec("measurement_voltage_pu"),
            VariableSpec("measurement_active_power"),
            VariableSpec("measurement_reactive_power"),
            VariableSpec("time_seconds"),
        )

    def output_specs(self) -> tuple[VariableSpec, ...]:
        return (
            VariableSpec("command_active_power"),
            VariableSpec("command_reactive_power"),
            VariableSpec("command_enabled", val=1.0),
            VariableSpec("diagnostic_residual"),
        )

    def compute_commands(self, inputs) -> Mapping[str, Any]:
        settings = self.options["settings"] or {}
        voltage = float(inputs["measurement_voltage_pu"])
        active = float(inputs["measurement_active_power"])
        reactive = float(inputs["measurement_reactive_power"])
        time = float(inputs["time_seconds"])
        state = self._state

        uv2 = float(settings.get("uv_2_pu", 0.45))
        uv1 = float(settings.get("uv_1_pu", 0.70))
        ov1 = float(settings.get("ov_1_pu", 1.10))
        ov2 = float(settings.get("ov_2_pu", 1.20))
        uv2_time = float(settings.get("uv_2_ct_sec", 0.16))
        uv1_time = float(settings.get("uv_1_ct_sec", 2.0))
        ov1_time = float(settings.get("ov_1_ct_sec", 2.0))
        ov2_time = float(settings.get("ov_2_ct_sec", 0.16))
        deadtime = float(settings.get("reconnect_deadtime_sec", 300.0))
        pmax_time = float(settings.get("reconnect_pmax_time_sec", 300.0))

        if voltage < uv2 or voltage > ov2:
            trip_delay = uv2_time if voltage < uv2 else ov2_time
            region = "trip"
        elif voltage < uv1 or voltage > ov1:
            trip_delay = uv1_time if voltage < uv1 else ov1_time
            region = "ride_through"
        else:
            trip_delay = None
            region = "normal"

        violation_start = state["violation_start"]
        if region != "normal" and violation_start is None:
            violation_start = time
        if region == "normal":
            violation_start = None

        connected = bool(state["connected"])
        reconnect_start = state["reconnect_start"]
        if connected and region == "trip" and violation_start is not None:
            connected = time - violation_start < trip_delay
            if not connected:
                reconnect_start = time
        elif not connected and region == "normal":
            if reconnect_start is None:
                reconnect_start = time
            connected = time - reconnect_start >= deadtime
        elif connected:
            reconnect_start = None

        if not connected:
            active_command = reactive_command = 0.0
        elif region == "ride_through":
            active_command = 0.0 if voltage < uv1 or voltage > ov1 else active
            reactive_command = reactive
        else:
            active_command, reactive_command = active, reactive

        pending = dict(state)
        pending.update(
            connected=connected,
            violation_start=violation_start,
            reconnect_start=reconnect_start,
            last_time=time,
        )
        self._pending_state = pending
        return {
            "command_active_power": active_command,
            "command_reactive_power": reactive_command,
            "command_enabled": float(connected),
            "diagnostic_residual": 0.0,
        }

    def commit_step(self) -> None:
        if self._pending_state is not None:
            self._state = self._pending_state
            self._pending_state = None
        self._step_count += 1

    @property
    def step_count(self) -> int:
        return self._step_count
