# Vectorized batch implementation of MotorStall controller
# Holds all motor state as numpy arrays; computes all 200+ motors in one
# vectorized pass, then writes results back individually.

import math
import random

import numpy as np
from loguru import logger

from pydss.pyControllers.models import MotorStallSettings


class MotorStallBatch:
    """Drop-in replacement that processes ALL MotorStall controllers in one
    vectorized numpy pass per timestep.

    Expected by dssInstance: .Update(Priority, time, update_results) -> 0
                             .Name() -> str
                             .ControlledElement() -> str (first element)
                             .ACTIVE_PRIORITIES = (0,)
    """

    ACTIVE_PRIORITIES = (0,)

    def __init__(self, controllers):
        """Build from a list of already-constructed MotorStall instances.

        Parameters
        ----------
        controllers : list[MotorStall]
            The individual controller instances (we steal their DSS element
            refs and settings, then discard the Python-level Update loop).
        """
        n = len(controllers)
        if n == 0:
            raise ValueError("MotorStallBatch requires at least one controller")
        self._n = n
        self._names = [c.name for c in controllers]
        self._elements = [c._controlled_element for c in controllers]
        self._bus_objects = [c._controlled_element.sBus[0] for c in controllers]
        self._dss_solver = controllers[0]._dss_solver
        self._dss = controllers[0]._controlled_element._dssInstance

        # ---- per-motor scalar settings (turned into arrays) ----
        self._kw_rated = np.array([c.kw_rated for c in controllers])
        self._kvar_rated = np.array([c.kvar_rated for c in controllers])
        self._kva_rated = np.array([c.kva_rated for c in controllers])
        self._kvbase = np.array([c.kvbase for c in controllers])
        self._i_base = np.array([c.i_base for c in controllers])

        self._comp_lf = np.array([c.comp_lf for c in controllers])
        self._rated_pf = np.array([c.rated_pf for c in controllers])
        self._r_stall_pu = np.array([c.r_stall_pu for c in controllers])
        self._x_stall_pu = np.array([c.x_stall_pu for c in controllers])
        self._z2 = self._r_stall_pu ** 2 + self._x_stall_pu ** 2  # precompute

        self._v_stall = np.array([c._settings.v_stall for c in controllers])
        self._v_break = np.array([c._settings.v_break for c in controllers])
        self._lf_adj = np.array([c._settings.lf_adj for c in controllers])
        self._t_stall = np.array([c._settings.t_stall for c in controllers])
        self._v_rstrt = np.array([c._settings.v_rstrt for c in controllers])
        self._t_restart = np.array([c._settings.t_restart for c in controllers])
        self._f_rst = np.array([c._settings.f_rst for c in controllers])

        self._k_p1 = np.array([c._settings.k_p1 for c in controllers])
        self._n_p1 = np.array([c._settings.n_p1 for c in controllers])
        self._k_p2 = np.array([c._settings.k_p2 for c in controllers])
        self._n_p2 = np.array([c._settings.n_p2 for c in controllers])
        self._k_q1 = np.array([c._settings.k_q1 for c in controllers])
        self._n_q1 = np.array([c._settings.n_q1 for c in controllers])
        self._k_q2 = np.array([c._settings.k_q2 for c in controllers])
        self._n_q2 = np.array([c._settings.n_q2 for c in controllers])

        self._f_uvr = np.array([c.f_uvr for c in controllers])
        self._uv_tr1 = np.array([c.uv_tr1 for c in controllers])
        self._t_tr1 = np.array([c.t_tr1 for c in controllers])

        self._vc_1off = np.array([c.vc_1off for c in controllers])
        self._vc_2off = np.array([c.vc_2off for c in controllers])
        self._vc_1on = np.array([c.vc_1on for c in controllers])
        self._vc_2on = np.array([c.vc_2on for c in controllers])

        self._t_th = np.array([c.t_th for c in controllers])
        self._t_th1t = np.array([c._settings.t_th1t for c in controllers])
        self._t_th2t = np.array([c._settings.t_th2t for c in controllers])

        self._dt = np.array([c.dt for c in controllers])

        # ---- per-motor state ----
        self._stall = np.zeros(n, dtype=bool)
        self._stall_counting = np.zeros(n, dtype=bool)
        self._stall_time_start = np.zeros(n)

        self._rstrt = np.ones(n, dtype=bool)
        self._rstrt_counting = np.zeros(n, dtype=bool)
        self._rstrt_time_start = np.zeros(n)

        self._uv_trip = np.zeros(n, dtype=bool)
        self._uv_counting = np.zeros(n, dtype=bool)
        self._uv_time_start = np.zeros(n)

        self._voltage_prev = np.ones(n)

        init_i2r = 1.0 * 1.0 * self._r_stall_pu
        self._i2r_rstr_prev = init_i2r.copy()
        self._temp_rstr_prev = init_i2r.copy()
        self._i2r_nonrstr_prev = init_i2r.copy()
        self._temp_nonrstr_prev = init_i2r.copy()

        self._trip_rstr = np.zeros(n, dtype=bool)
        self._trip_nonrstr = np.zeros(n, dtype=bool)

        # Store full names for bulk command writes
        self._full_names = [elem._FullName for elem in self._elements]
        # valid mask: i_base != 0
        self._valid = self._i_base != 0.0

    # ---- Interface expected by dssInstance ----

    def Name(self):
        return "MotorStallBatch"

    def ControlledElement(self):
        return self._elements[0].GetInfo()[0] + "." + self._elements[0].GetInfo()[1]

    def debugInfo(self):
        return

    def Update(self, Priority, time_val, update_results):
        if Priority != 0:
            return 0

        n = self._n
        t_now = self._dss_solver.GetTotalSeconds()

        # ---- READ phase: per-element API calls ----
        voltage_pu = np.empty(n)
        for i in range(n):
            if not self._valid[i]:
                voltage_pu[i] = 1.0
                continue
            bus = self._bus_objects[i]
            bus.SetActiveObject()
            voltage_pu[i] = self._dss.Bus.puVmagAngle()[0]

        # ---- COMPUTE phase: fully vectorized ----
        v = voltage_pu
        v_prev = self._voltage_prev

        v_stall_adj = self._v_stall * (1.0 + self._lf_adj * (self._comp_lf - 1.0))
        v_break_adj = self._v_break * (1.0 + self._lf_adj * (self._comp_lf - 1.0))

        # -- stall timing --
        below_stall = (v < v_stall_adj) & (~self._stall)
        # motors that were already counting and still below stall
        counting_and_below = below_stall & self._stall_counting
        stall_time = t_now - self._stall_time_start
        newly_stalled = counting_and_below & (stall_time > self._t_stall) & (~self._stall)
        self._stall[newly_stalled] = True
        self._rstrt[newly_stalled] = False
        # motors that just started counting
        start_counting = below_stall & (~self._stall_counting)
        self._stall_time_start[start_counting] = t_now
        self._stall_counting[below_stall] = True
        # motors no longer below stall: reset counting
        self._stall_counting[~below_stall] = False

        # -- restart timing --
        above_rstrt = (v > self._v_rstrt) & (~self._rstrt)
        counting_and_above = above_rstrt & self._rstrt_counting
        rstrt_time = t_now - self._rstrt_time_start
        newly_restarted = counting_and_above & (rstrt_time > self._t_restart)
        self._rstrt[newly_restarted] = True
        start_rstrt_counting = above_rstrt & (~self._rstrt_counting)
        self._rstrt_time_start[start_rstrt_counting] = t_now
        self._rstrt_counting[above_rstrt] = True
        self._rstrt_counting[~above_rstrt] = False

        # -- UV trip --
        below_uv = (v < self._uv_tr1) & (~self._uv_trip)
        uv_counting_below = below_uv & self._uv_counting
        uv_time = t_now - self._uv_time_start
        newly_uv_tripped = uv_counting_below & (uv_time > self._t_tr1) & (~self._uv_trip)
        self._uv_trip[newly_uv_tripped] = True
        self._uv_counting[newly_uv_tripped] = False
        start_uv_counting = below_uv & (~self._uv_counting) & (~self._uv_trip)
        self._uv_time_start[start_uv_counting] = t_now
        self._uv_counting[start_uv_counting] = True

        Kthuv = np.where(self._uv_trip, 1.0 - self._f_uvr, 1.0)

        # -- contactor --
        rising = v_prev <= v
        # reconnect path
        Kthc_recon = np.where(v > self._vc_1on, 1.0,
                     np.where(v < self._vc_2on, 0.0,
                              (v - self._vc_2on) / (self._vc_1on - self._vc_2on)))
        # trip path
        Kthc_trip = np.where(v > self._vc_1off, 1.0,
                   np.where(v < self._vc_2off, 0.0,
                            (v - self._vc_2off) / (self._vc_1off - self._vc_2off)))
        Kthc = np.where(rising, Kthc_recon, Kthc_trip)

        # -- p0, q0 --
        p0 = 1.0 - self._k_p1 * (1.0 - v_break_adj) ** self._n_p1
        q0 = (np.sqrt(1.0 - self._rated_pf ** 2) / self._rated_pf
              - self._k_q1 * (1.0 - v_break_adj) ** self._n_q1)

        # -- stall power --
        p_stall = v ** 2 * self._r_stall_pu / self._z2
        q_stall = v ** 2 * self._x_stall_pu / self._z2

        # -- running power (stage I or II) --
        above_break = v > v_break_adj
        p_run = np.where(above_break,
                         p0 + self._k_p1 * (v - v_break_adj) ** self._n_p1,
                         p0 + self._k_p2 * (v_break_adj - v) ** self._n_p2)
        q_run = np.where(above_break,
                         q0 + self._k_q1 * (v - v_break_adj) ** self._n_q1,
                         q0 + self._k_q2 * (v_break_adj - v) ** self._n_q2)

        # Decide p_rstrt, q_rstrt, p_nonrstrt, q_nonrstrt and thermal inputs
        # Case 1: stall=True, rstrt=True  (stage III restarted)
        # Case 2: stall=True, rstrt=False (stage III not restarted)
        # Case 3: stall=False             (stage I/II)

        case1 = self._stall & self._rstrt
        case2 = self._stall & (~self._rstrt)
        case3 = ~self._stall

        # Initialize output arrays
        p_rstrt = np.empty(n)
        q_rstrt = np.empty(n)
        p_nonrstrt = np.empty(n)
        q_nonrstrt = np.empty(n)
        i2r_rstr = np.empty(n)
        i2r_nonrstr = np.empty(n)

        # Case 1: stall + restart
        if case1.any():
            cur_nonrstrt_1 = v[case1] / np.sqrt(self._z2[case1])
            cur_rstrt_1 = p_run[case1] / v[case1]
            i2r_rstr[case1] = cur_rstrt_1 ** 2 * self._r_stall_pu[case1]
            i2r_nonrstr[case1] = cur_nonrstrt_1 ** 2 * self._r_stall_pu[case1]
            p_rstrt[case1] = p_run[case1] * self._f_rst[case1]
            q_rstrt[case1] = q_run[case1] * self._f_rst[case1]
            p_nonrstrt[case1] = p_stall[case1] * (1.0 - self._f_rst[case1])
            q_nonrstrt[case1] = q_stall[case1] * (1.0 - self._f_rst[case1])

        # Case 2: stall + not restart
        if case2.any():
            cur_2 = v[case2] / np.sqrt(self._z2[case2])
            i2r_rstr[case2] = cur_2 ** 2 * self._r_stall_pu[case2]
            i2r_nonrstr[case2] = cur_2 ** 2 * self._r_stall_pu[case2]
            p_rstrt[case2] = p_stall[case2] * self._f_rst[case2]
            q_rstrt[case2] = q_stall[case2] * self._f_rst[case2]
            p_nonrstrt[case2] = p_stall[case2] * (1.0 - self._f_rst[case2])
            q_nonrstrt[case2] = q_stall[case2] * (1.0 - self._f_rst[case2])

        # Case 3: not stalled
        if case3.any():
            cur_3 = p_run[case3] / v[case3]
            i2r_rstr[case3] = cur_3 ** 2 * self._r_stall_pu[case3]
            i2r_nonrstr[case3] = cur_3 ** 2 * self._r_stall_pu[case3]
            p_rstrt[case3] = p_run[case3] * self._f_rst[case3]
            q_rstrt[case3] = q_run[case3] * self._f_rst[case3]
            p_nonrstrt[case3] = p_run[case3] * (1.0 - self._f_rst[case3])
            q_nonrstrt[case3] = q_run[case3] * (1.0 - self._f_rst[case3])

        # -- thermal update (bilinear transform) --
        temp_rstr = (self._dt * (i2r_rstr + self._i2r_rstr_prev) -
                     (self._dt - 2.0 * self._t_th) * self._temp_rstr_prev) / (2.0 * self._t_th + self._dt)
        temp_nonrstr = (self._dt * (i2r_nonrstr + self._i2r_nonrstr_prev) -
                        (self._dt - 2.0 * self._t_th) * self._temp_nonrstr_prev) / (2.0 * self._t_th + self._dt)

        # -- thermal protection --
        # Only applies when stalled
        stalled = self._stall

        # restartable fraction thermal
        Kth_rstr = np.ones(n)
        tripped_rstr = self._trip_rstr & stalled
        Kth_rstr[tripped_rstr] = 0.0
        newly_trip_rstr = (~self._trip_rstr) & stalled & (temp_rstr > self._t_th2t)
        self._trip_rstr[newly_trip_rstr] = True
        Kth_rstr[newly_trip_rstr] = 0.0
        partial_rstr = (~self._trip_rstr) & stalled & (temp_rstr > self._t_th1t) & (temp_rstr <= self._t_th2t)
        Kth_rstr[partial_rstr] = 1.0 - (temp_rstr[partial_rstr] - self._t_th1t[partial_rstr]) / (self._t_th2t[partial_rstr] - self._t_th1t[partial_rstr])

        # non-restartable fraction thermal
        Kth_nonrstr = np.ones(n)
        tripped_nonrstr = self._trip_nonrstr & stalled
        Kth_nonrstr[tripped_nonrstr] = 0.0
        newly_trip_nonrstr = (~self._trip_nonrstr) & stalled & (temp_nonrstr > self._t_th2t)
        self._trip_nonrstr[newly_trip_nonrstr] = True
        Kth_nonrstr[newly_trip_nonrstr] = 0.0
        partial_nonrstr = (~self._trip_nonrstr) & stalled & (temp_nonrstr > self._t_th1t) & (temp_nonrstr <= self._t_th2t)
        Kth_nonrstr[partial_nonrstr] = 1.0 - (temp_nonrstr[partial_nonrstr] - self._t_th1t[partial_nonrstr]) / (self._t_th2t[partial_nonrstr] - self._t_th1t[partial_nonrstr])

        # -- final power setpoints --
        pset = (Kth_rstr * p_rstrt + Kth_nonrstr * p_nonrstrt) * self._kw_rated
        qset = (Kth_rstr * q_rstrt + Kth_nonrstr * q_nonrstrt) * self._kw_rated
        pset_final = Kthc * Kthuv * pset
        qset_final = Kthc * Kthuv * qset

        # ---- WRITE phase: per-element API calls ----
        dss = self._dss
        run_cmd = dss.utils.run_command
        for i in range(n):
            if not self._valid[i]:
                continue
            fname = self._full_names[i]
            run_cmd(f"{fname}.kw={pset_final[i]}")
            run_cmd(f"{fname}.kvar={qset_final[i]}")

        # ---- update state for next step ----
        self._voltage_prev[:] = v
        self._temp_rstr_prev[:] = temp_rstr
        self._i2r_rstr_prev[:] = i2r_rstr
        self._temp_nonrstr_prev[:] = temp_nonrstr
        self._i2r_nonrstr_prev[:] = i2r_nonrstr

        return 0
