# Vectorized batch implementation of PvVoltageRideThru controller
#
# Processes all PV ride-through controllers in a single pass per priority,
# reading voltage once per priority call to eliminate redundant API calls.
# Pre-caches kVBase (constant during simulation) to halve voltage reads.

import numpy as np
from loguru import logger

from pydss.pyControllers.Controllers.PvVoltageRideThru import _point_in_any_polygon
from pydss.pyControllers.enumerations import (
    PvStandard,
    VoltageCalcModes,
    MultipleDisturbances,
)


class PvVoltageRideThruBatch:
    """Drop-in replacement that processes ALL PvVoltageRideThru controllers
    in a single pass per priority, minimizing redundant OpenDSS API calls.

    Compared to running N individual PvVoltageRideThru controllers:
    - Reads voltage once per priority instead of 2-3 times (saves ~N API calls)
    - Pre-caches kVBase so no per-step kVBase reads (saves 2*N API calls)
    - Eliminates redundant voltage read inside _trip() (saves N API calls)
    - Uses run_command for writes (same as individual)
    - Vectorizes timer updates and reconnect ramp with numpy

    Expected by dssInstance: .Update(Priority, time, update_results) -> 0
                             .Name() -> str
                             .ControlledElement() -> str
                             .ACTIVE_PRIORITIES = (0, 2)
    """

    ACTIVE_PRIORITIES = (0, 2)

    def __init__(self, controllers):
        """Build from a list of already-constructed PvVoltageRideThru instances.

        Parameters
        ----------
        controllers : list[PvVoltageRideThru]
            The individual controller instances whose state and settings
            are transferred into vectorized arrays.
        """
        n = len(controllers)
        if n == 0:
            raise ValueError("PvVoltageRideThruBatch requires at least one controller")
        self._n = n

        self._elements = [c._controlled_element for c in controllers]
        # Access name-mangled __dss_solver via Python name mangling
        self._dss_solver = controllers[0]._PvVoltageRideThru__dss_solver
        self._dss = controllers[0]._controlled_element._dssInstance
        self._full_names = [elem._FullName for elem in self._elements]

        # Pre-cache kVBase in volts (constant during simulation)
        self._u_base = np.array([
            c._controlled_element.sBus[0].GetVariable('kVBase') * 1000
            for c in controllers
        ])

        # Voltage calc mode: True=max, False=avg
        self._use_max_voltage = np.array([
            c._voltage_calc_mode == VoltageCalcModes.MAX for c in controllers
        ])

        # ---- Per-controller settings → arrays ----
        self._p_rated = np.array([c._p_rated for c in controllers])
        self._rvs_upper = np.array([c._rvs[0] for c in controllers])
        self._rvs_lower = np.array([c._rvs[1] for c in controllers])
        self._trip_deadtime_sec = np.array([c._trip_deadtime_sec for c in controllers])
        self._time_to_p_max_sec = np.array([c._time_to_p_max_sec for c in controllers])

        self._step_size_sec = self._dss_solver.GetStepSizeSec()

        # Per-controller polygon data (lists; empty for 2003 controllers)
        self._curr_lim_polys_list = [
            getattr(c, '_curr_lim_polys', []) for c in controllers
        ]
        self._momentary_polys_list = [
            getattr(c, '_momentary_polys', []) for c in controllers
        ]
        self._trip_polys_list = [
            getattr(c, '_trip_polys', []) for c in controllers
        ]

        # Standard flags
        self._is_1547_2018 = [
            c.model.follow_standard == PvStandard.IEEE_1547_2018
            for c in controllers
        ]
        self._is_1547_2003 = [
            c.model.follow_standard == PvStandard.IEEE_1547_2003
            for c in controllers
        ]
        self._multiple_dist_trip = [
            getattr(c.model, 'multiple_disturdances', None) == MultipleDisturbances.TRIP
            for c in controllers
        ]

        # Fault counter limits
        self._fault_counter_max = np.array([
            getattr(c, '_fault_counter_max', 0) for c in controllers
        ])
        self._fault_counter_clearing_time_sec = np.array([
            getattr(c, '_fault_counter_clearing_time_sec', 0)
            for c in controllers
        ])

        # ---- State arrays (float seconds instead of datetime) ----
        t_now = self._dss_solver.GetTotalSeconds()
        self._is_connected = np.ones(n, dtype=bool)
        self._p_limit = self._p_rated.copy()
        self._reconnect_start_time = t_now - self._time_to_p_max_sec
        self._tripped_p_max_delay = np.zeros(n)
        self._tripped_dead_time = np.zeros(n)
        self._tripped_start_time = np.full(n, t_now)
        self._normal_operation = np.ones(n, dtype=bool)
        self._normal_operation_start_time = np.full(n, t_now)
        self._u_violation_time = np.full(n, 99999.0)
        self._voltage_violation_m = np.zeros(n, dtype=bool)
        self._fault_counter = np.zeros(n, dtype=int)
        self._is_in_continuous_region = np.ones(n, dtype=bool)
        self._fault_window_clearing_start_time = np.full(n, t_now)
        self._uViolation_start_time = np.full(n, t_now)

        # Region history: (n, 3) - rotation matches original's list rotation
        self._region = np.full((n, 3), 3, dtype=int)

        logger.info(
            f"PvVoltageRideThruBatch created with {n} controllers, "
            f"2018: {sum(self._is_1547_2018)}, 2003: {sum(self._is_1547_2003)}"
        )

    # ---- Interface expected by dssInstance ----

    def Name(self):
        return "PvVoltageRideThruBatch"

    def ControlledElement(self):
        info = self._elements[0].GetInfo()
        return f"{info[0]}.{info[1]}"

    def debugInfo(self):
        return []

    def _read_voltages(self):
        """Read per-unit voltage for each controller.

        Uses the element's VoltagesMagAng (same as original) but with
        pre-cached kVBase to avoid per-step bus reads.
        """
        n = self._n
        v = np.empty(n)
        for i in range(n):
            v_mag = self._elements[i].GetVariable('VoltagesMagAng')[::2]
            if self._use_max_voltage[i]:
                v[i] = max(v_mag) / self._u_base[i]
            else:
                v[i] = sum(v_mag) / (self._u_base[i] * len(v_mag))
        return v

    def Update(self, priority, time_val, update_results):
        if priority == 0:
            self._update_connect()
        elif priority == 2:
            self._update_ride_through()
        return 0

    def _update_connect(self):
        """Priority 0: reconnect and power ramp logic."""
        t_now = self._dss_solver.GetTotalSeconds()
        u_in = self._read_voltages()
        run_cmd = self._dss.utils.run_command

        # Snapshot disconnected state before modifications
        was_disconnected = ~self._is_connected.copy()

        # --- Disconnected controllers: check reconnect conditions ---
        deadtime = t_now - self._tripped_start_time
        in_range = (u_in < self._rvs_upper) & (u_in > self._rvs_lower)
        can_reconnect = was_disconnected & in_range & (deadtime >= self._tripped_dead_time)

        if can_reconnect.any():
            for i in np.where(can_reconnect)[0]:
                run_cmd(f"{self._full_names[i]}.enabled=yes")
                run_cmd(f"{self._full_names[i]}.kw=0")
            self._is_connected[can_reconnect] = True
            self._reconnect_start_time[can_reconnect] = t_now

        # --- Already connected controllers: compute ramp and set kw ---
        already_connected = self._is_connected & ~can_reconnect
        if already_connected.any():
            idx = np.where(already_connected)[0]
            conntime = t_now - self._reconnect_start_time[idx]
            delay = self._tripped_p_max_delay[idx]
            rated = self._p_rated[idx]
            ramping = conntime < delay
            p_lim = np.where(
                ramping,
                conntime / np.maximum(delay, 1e-30) * rated,
                rated,
            )
            self._p_limit[idx] = p_lim
            for i in idx:
                run_cmd(f"{self._full_names[i]}.kw={self._p_limit[i]}")

    def _update_ride_through(self):
        """Priority 2: violation timers and voltage ride-through logic."""
        n = self._n
        t_now = self._dss_solver.GetTotalSeconds()
        u_in = self._read_voltages()
        run_cmd = self._dss.utils.run_command

        # ---- Update violation timers (vectorized) ----
        in_normal = (u_in < self._rvs_upper) & (u_in > self._rvs_lower)

        # Transition to normal voltage
        just_normal = in_normal & ~self._normal_operation
        self._normal_operation[in_normal] = True
        self._normal_operation_start_time[just_normal] = t_now
        self._voltage_violation_m[in_normal] = False

        # Transition to abnormal voltage
        abnormal = ~in_normal
        just_abnormal = abnormal & ~self._voltage_violation_m
        self._voltage_violation_m[abnormal] = True
        self._uViolation_start_time[just_abnormal] = t_now
        self._u_violation_time[just_abnormal] = 0.0
        already_abnormal = abnormal & ~just_abnormal
        self._u_violation_time[already_abnormal] = (
            t_now - self._uViolation_start_time[already_abnormal]
        )

        # ---- Ride-through logic (per-controller for polygon checks) ----
        new_region = np.full(n, 3, dtype=int)
        new_is_continuous = np.ones(n, dtype=bool)

        for i in range(n):
            # IEEE 1547-2003: simple undervoltage trip
            if self._is_1547_2003[i]:
                if u_in[i] < 0.88 and self._is_connected[i]:
                    run_cmd(f"{self._full_names[i]}.kw=0")
                    self._is_connected[i] = False
                    self._tripped_start_time[i] = t_now
                    self._tripped_p_max_delay[i] = 0.4
                    self._tripped_dead_time[i] = 30.0
                continue

            if not self._is_1547_2018[i]:
                continue

            pt_t = self._u_violation_time[i]
            pt_v = u_in[i]

            if _point_in_any_polygon(pt_t, pt_v, self._curr_lim_polys_list[i]):
                new_region[i] = 0
                new_is_continuous[i] = False

            elif (self._momentary_polys_list[i] and
                  _point_in_any_polygon(pt_t, pt_v, self._momentary_polys_list[i])):
                new_region[i] = 1
                new_is_continuous[i] = False
                # Momentary: only trip if currently connected
                if self._is_connected[i]:
                    run_cmd(f"{self._full_names[i]}.kw=0")
                    self._is_connected[i] = False
                    self._tripped_start_time[i] = t_now
                    self._tripped_p_max_delay[i] = 0.5
                    self._tripped_dead_time[i] = self._step_size_sec

            elif _point_in_any_polygon(pt_t, pt_v, self._trip_polys_list[i]):
                new_region[i] = 2
                new_is_continuous[i] = False
                # Trip region: always trip (forceTrip or permissive_to_trip
                # both result in tripping regardless of connected state)
                run_cmd(f"{self._full_names[i]}.kw=0")
                self._is_connected[i] = False
                self._tripped_start_time[i] = t_now
                self._tripped_p_max_delay[i] = self._time_to_p_max_sec[i]
                self._tripped_dead_time[i] = self._trip_deadtime_sec[i]
            # else: continuous region (region=3), no action

        # ---- Update region history ----
        # Original rotation: [a,b,c] → [b,c,a] then [0]=new
        # Result: [new, old[2], old[0]]
        old_0 = self._region[:, 0].copy()
        old_2 = self._region[:, 2].copy()
        self._region[:, 0] = new_region
        self._region[:, 1] = old_2
        self._region[:, 2] = old_0

        # ---- Fault counter logic (vectorized where possible) ----
        # Transition: non-continuous → continuous (fault window clearing starts)
        to_continuous = new_is_continuous & ~self._is_in_continuous_region
        self._fault_window_clearing_start_time[to_continuous] = t_now

        clearing_time = t_now - self._fault_window_clearing_start_time

        # Transition: continuous → non-continuous (new fault event)
        from_continuous = self._is_in_continuous_region & ~new_is_continuous
        within_window = from_continuous & (
            clearing_time <= self._fault_counter_clearing_time_sec
        )
        self._fault_counter[within_window] += 1

        # Fault counter exceeded max → trip if configured
        exceeded = within_window & (self._fault_counter > self._fault_counter_max)
        if exceeded.any():
            for i in np.where(exceeded)[0]:
                if self._multiple_dist_trip[i]:
                    run_cmd(f"{self._full_names[i]}.kw=0")
                    self._is_connected[i] = False
                    self._tripped_start_time[i] = t_now
                    self._tripped_p_max_delay[i] = self._time_to_p_max_sec[i]
                    self._tripped_dead_time[i] = self._trip_deadtime_sec[i]
                    self._fault_counter[i] = 0

        # Clear counter if clearing time exceeded
        clear_counter = (
            (clearing_time > self._fault_counter_clearing_time_sec) &
            (self._fault_counter > 0)
        )
        self._fault_counter[clear_counter] = 0

        self._is_in_continuous_region[:] = new_is_continuous
