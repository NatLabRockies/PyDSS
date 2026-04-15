#Algebraic model for Type D motor - residential air conditioner

import scipy.signal as signal
import numpy as np
import math
import os
from loguru import logger
import random

from pydss.pyControllers.models import MotorStallSettings
from pydss.pyControllers.pyControllerAbstract import ControllerAbstract

class MotorStall(ControllerAbstract):   
    def __init__(self, motor_obj, settings, dss_instance, elm_object_list, dss_solver):
        super(MotorStall, self).__init__(motor_obj, settings, dss_instance, elm_object_list, dss_solver)

        self._class, self._name = motor_obj.GetInfo()
        assert self._class == "Load", "Motor stall model can only be used with load models"
        assert motor_obj.NumPhases == 1, "Motor stall model can only be used with single phase loads"
        
        self.name = "Controller-{}-{}".format(self._class, self._name)
        self._controlled_element = motor_obj
        self._settings = MotorStallSettings(**settings)
        self._dss_solver = dss_solver
        self.mode = 1
        self.model_mode = self._controlled_element.SetParameter('model', self.mode) # 3 - motor, 1 - Standard constant P+jQ
        self.load_mult = dss_instance.Solution.LoadMult()
        self._controlled_element.SetParameter('vminpu', 0.0)

        self.kw_rated = self._controlled_element.GetParameter('kw')
        self.kvar_rated = self._controlled_element.GetParameter('kvar')
        self.rated_pf = self._settings.rated_pf
        self.comp_lf = self._settings.comp_lf
        # self.kva_rated = self.kw_rated / self.comp_lf
        self.kva_rated = math.sqrt(self.kw_rated*self.kw_rated + self.kvar_rated*self.kvar_rated)
            
        self.stall_time_start = 0
        self.stall = False
        self.stall_counting = False

        self.rstrt_time_start = 0
        self.rstrt = True
        self.rstrt_counting = False

        self.uv_time_start = 0
        self.uv_trip = False
        self.uv_counting = False
        self.f_uvr = self._settings.f_uvr
        self.uv_tr1 = self._settings.uv_tr1
        self.t_tr1 = self._settings.t_tr1

        self.vc_1off = self._settings.vc_1off
        self.vc_2off = self._settings.vc_2off
        self.vc_1on = self._settings.vc_1on
        self.vc_2on = self._settings.vc_2on

        self.r_stall_pu = self._settings.r_stall_pu
        self.x_stall_pu = self._settings.x_stall_pu
        

        self.va_base = 100 * 1e6
        self.kvbase = self._controlled_element.sBus[0].GetVariable("kVBase")
        self.i_base = self.kva_rated / self.kvbase

        self.dt = dss_solver.GetStepResolutionSeconds()
        self.t_th = self._settings.t_th
        self.i2r_rstr_prev = 1*1*self.r_stall_pu
        self.temp_rstr_prev = self.i2r_rstr_prev
        self.i2r_nonrstr_prev = 1*1*self.r_stall_pu
        self.temp_nonrstr_prev = self.i2r_nonrstr_prev

        self.voltage_prev = 1.0
        self.i2r_rstr = 0
        self.temp_rstr = self.temp_rstr_prev
        self.i2r_nonrstr = 0
        self.temp_nonrstr = self.temp_nonrstr_prev
        self.trip_rstr = False
        self.trip_nonrstr = False
        self.thermal_threshold = self._settings.t_th1t + (self._settings.t_th2t-self._settings.t_th1t)*random.random()
        
        return
    
    def Name(self):
        return self.name

    def ControlledElement(self):
        return "{}.{}".format(self._class, self._name)

    def debugInfo(self):
        return 

    def Update(self, Priority, time, update_results):
        self.t = self._dss_solver.GetTotalSeconds()
        logger.debug(f"self.t: {self.t}")
        logger.debug(f"self._controlled_element: {self._controlled_element}")
        logger.debug(f"{self.name} - {self.kw_rated} - {self.kvar_rated} - {self.kvbase} - {self.i_base}")
        if self.i_base:
            self.p = self._controlled_element.GetVariable('Powers')[0] + self._controlled_element.GetVariable('Powers')[2]
            self.q = self._controlled_element.GetVariable('Powers')[1] + self._controlled_element.GetVariable('Powers')[3]
            self.voltage = self._controlled_element.GetVariable('VoltagesMagAng')[0]
            self.voltage_pu = self._controlled_element.sBus[0].GetVariable("puVmagAngle")[0]
            logger.debug(f"CurrentsMagAng: {self._controlled_element.GetVariable('CurrentsMagAng')}")
            logger.debug(f"voltage_pu: {self.voltage_pu}")
            logger.debug(f"Powers: {self._controlled_element.GetVariable('Powers')}")
            logger.debug(f"self.kw_rated: {self.kw_rated}")
            logger.debug(f"self.kvar_rated: {self.kvar_rated}")

            comp_lf = self.comp_lf # self.p / self.kw_rated
            comp_pf = self.rated_pf # self.p / (self.p**2 + self.q**2)**0.5
            
            v_stall_adj = self._settings.v_stall*(1 + self._settings.lf_adj * (comp_lf-1))
            v_break_adj = self._settings.v_break*(1 + self._settings.lf_adj * (comp_lf-1))

            if Priority == 0:
                ## stall and restart time clock
                if self.voltage_pu < v_stall_adj and not self.stall:
                    if self.stall_counting:
                        self.stall_time = self._dss_solver.GetTotalSeconds() - self.stall_time_start
                        if self.stall_time > self._settings.t_stall and not self.stall:
                            self.stall = True
                            self.rstrt = False
                    else:
                        self.stall_time_start = self._dss_solver.GetTotalSeconds()
                        self.stall_counting = True
                else:
                    self.stall_counting = False
                if self.voltage_pu > self._settings.v_rstrt and not self.rstrt:
                    if self.rstrt_counting:
                        self.rstrt_time = self._dss_solver.GetTotalSeconds() - self.rstrt_time_start
                        if self.rstrt_time > self._settings.t_restart:
                            self.rstrt = True
                    else:
                        self.rstrt_time_start = self._dss_solver.GetTotalSeconds()
                        self.rstrt_counting = True
                else:
                    self.rstrt_counting = False
                
                ## uv trip
                if self.voltage_pu < self.uv_tr1 and not self.uv_trip:
                    if self.uv_counting:
                        self.uv_time = self._dss_solver.GetTotalSeconds() - self.uv_time_start
                        if self.uv_time > self.t_tr1 and not self.uv_trip:
                            self.uv_trip = True
                            self.uv_counting = False
                    else:
                        self.uv_time_start = self._dss_solver.GetTotalSeconds()
                        self.uv_counting = True
                if self.uv_trip:
                    Kthuv = 1.0 - self.f_uvr
                else:
                    Kthuv = 1.0
                # logger.info(f"Kthuv: {Kthuv}")

                ## v contactor trip
                if self.voltage_prev <= self.voltage_pu:
                    ## reconnect
                    if self.voltage_pu > self.vc_1on:
                        Kthc = 1.0
                    elif self.voltage_pu < self.vc_2on:
                        Kthc = 0.0
                    else:
                        Kthc = (self.voltage_pu - self.vc_2on)/(self.vc_1on - self.vc_2on)
                else:
                    ## trip
                    if self.voltage_pu > self.vc_1off:
                        Kthc = 1.0
                    elif self.voltage_pu < self.vc_2off:
                        Kthc = 0.0
                    else:
                        Kthc = (self.voltage_pu - self.vc_2off)/(self.vc_1off - self.vc_2off)
                # logger.info(f"Kthc: {Kthc}")

                p0 = 1 - self._settings.k_p1 * (1-v_break_adj)**self._settings.n_p1
                q0 = ((1 - comp_pf**2)**0.5 / comp_pf)-self._settings.k_q1*(1-v_break_adj)**self._settings.n_q1
                logger.info(f"self.voltage_pu: {self.voltage_pu}")

                # the operation model
                if self.stall:
                    # stage III
                    p_stall = self.voltage_pu ** 2 * self.r_stall_pu / (self.r_stall_pu ** 2 + self.x_stall_pu ** 2)
                    q_stall = self.voltage_pu ** 2 * self.x_stall_pu / (self.r_stall_pu ** 2 + self.x_stall_pu ** 2)

                    if self.rstrt:
                        logger.info(f"Stage III: Motor stall and {self._settings.f_rst} of load is restarted")
                        if self.voltage_pu > v_break_adj:
                            p = p0 + self._settings.k_p1*(self.voltage_pu-v_break_adj)**self._settings.n_p1
                            q = q0 + self._settings.k_q1*(self.voltage_pu-v_break_adj)**self._settings.n_q1
                        else:
                            p = p0 + self._settings.k_p2 * (v_break_adj - self.voltage_pu)**self._settings.n_p2
                            q = q0 + self._settings.k_q2 * (v_break_adj - self.voltage_pu)**self._settings.n_q2
                        # self._controlled_element.SetParameter('kw', Kth * self.kw_rated * p_rstrt * self._settings.f_rst + Kth * p * self.kva_rated * (1-self._settings.f_rst)) 
                        # self._controlled_element.SetParameter('kvar', Kth * self.kvar_rated * q_rstrt * self._settings.f_rst + Kth * q * self.kva_rated * (1-self._settings.f_rst))
                        current_pu_nonrstrt = self.voltage_pu / math.sqrt(self.r_stall_pu ** 2 + self.x_stall_pu ** 2)
                        current_pu_rstrt = p / self.voltage_pu
                        self.i2r_rstr = current_pu_rstrt * current_pu_rstrt * self.r_stall_pu
                        self.i2r_nonrstr = current_pu_nonrstrt * current_pu_nonrstrt * self.r_stall_pu
                        self.temp_rstr = (self.dt*(self.i2r_rstr+self.i2r_rstr_prev)-(self.dt-2*self.t_th)*self.temp_rstr_prev)/(2*self.t_th+self.dt)
                        self.temp_nonrstr = (self.dt*(self.i2r_nonrstr+self.i2r_nonrstr_prev)-(self.dt-2*self.t_th)*self.temp_nonrstr_prev)/(2*self.t_th+self.dt)
                        p_rstrt = p * self._settings.f_rst
                        q_rstrt = q * self._settings.f_rst
                        p_nonrstrt = p_stall * (1 - self._settings.f_rst)
                        q_nonrstrt = q_stall * (1 - self._settings.f_rst)

                    else:
                        logger.info(f"Stage III: Motor stall and not restarted load")
                        # self._controlled_element.SetParameter('kw', Kth * p_stall * self.kva_rated) 
                        # self._controlled_element.SetParameter('kvar', Kth * q_stall * self.kva_rated)
                        p_rstrt = p_stall * self._settings.f_rst
                        q_rstrt = q_stall * self._settings.f_rst
                        p_nonrstrt = p_stall * (1 - self._settings.f_rst)
                        q_nonrstrt = q_stall * (1 - self._settings.f_rst)
                        current_pu = self.voltage_pu / math.sqrt(self.r_stall_pu ** 2 + self.x_stall_pu ** 2)
                        self.i2r_rstr = current_pu * current_pu * self.r_stall_pu
                        self.i2r_nonrstr = current_pu * current_pu * self.r_stall_pu
                        self.temp_rstr = (self.dt*(self.i2r_rstr+self.i2r_rstr_prev)-(self.dt-2*self.t_th)*self.temp_rstr_prev)/(2*self.t_th+self.dt)
                        self.temp_nonrstr = (self.dt*(self.i2r_nonrstr+self.i2r_nonrstr_prev)-(self.dt-2*self.t_th)*self.temp_nonrstr_prev)/(2*self.t_th+self.dt)
                        # logger.info(f"p_rstrt: {p_rstrt}")
                        # logger.info(f"q_rstrt: {q_rstrt}")
                        # logger.info(f"p_nonrstrt: {p_nonrstrt}")
                        # logger.info(f"q_nonrstrt: {q_nonrstrt}")
                        # logger.info(f"current_pu: {current_pu}")
                        # logger.info(f"self.i2r_rstr: {self.i2r_rstr}")
                        # logger.info(f"self.temp_rstr: {self.temp_rstr}")
                else:
                    if self.voltage_pu > v_break_adj:
                        # stage I
                        logger.info(f"Stage I: normal operation")
                        p = p0 + self._settings.k_p1*(self.voltage_pu-v_break_adj)**self._settings.n_p1
                        q = q0 + self._settings.k_q1*(self.voltage_pu-v_break_adj)**self._settings.n_q1
                    else:
                        # stage II or before stall
                        logger.info(f"Stage II: Motor voltage below the break down voltage")
                        p = p0 + self._settings.k_p2 * (v_break_adj - self.voltage_pu)**self._settings.n_p2
                        q = q0 + self._settings.k_q2 * (v_break_adj - self.voltage_pu)**self._settings.n_q2
                    current_pu = p / self.voltage_pu
                    p_rstrt = p * self._settings.f_rst
                    p_nonrstrt = p * (1 - self._settings.f_rst)
                    q_rstrt = q * self._settings.f_rst
                    q_nonrstrt = q * (1 - self._settings.f_rst)
                    self.i2r_rstr = current_pu * current_pu * self.r_stall_pu
                    self.i2r_nonrstr = current_pu * current_pu * self.r_stall_pu
                    self.temp_rstr = (self.dt*(self.i2r_rstr+self.i2r_rstr_prev)-(self.dt-2*self.t_th)*self.temp_rstr_prev)/(2*self.t_th+self.dt)
                    self.temp_nonrstr = (self.dt*(self.i2r_nonrstr+self.i2r_nonrstr_prev)-(self.dt-2*self.t_th)*self.temp_nonrstr_prev)/(2*self.t_th+self.dt)

                # thermal protection
                if self.stall:
                    if self.trip_rstr:
                        logger.debug(f"Motor is tripped")
                        Kth_rstr = 0
                    ## for single bus system
                    elif self.temp_rstr > self._settings.t_th2t:
                        self.trip_rstr = True
                        Kth_rstr = 0
                    elif self.temp_rstr > self._settings.t_th1t and self.temp_rstr <= self._settings.t_th2t:
                        Kth_rstr = 1 - (self.temp_rstr - self._settings.t_th1t)/(self._settings.t_th2t - self._settings.t_th1t)
                    # ## for multiple bus system
                    # elif self.temp_rstr > self.thermal_threshold:
                    #     self.trip_rstr = True
                    #     Kth_rstr = 0
                    else:
                        Kth_rstr = 1
                    
                    if self.trip_nonrstr:
                        logger.info(f"Motor is tripped")
                        Kth_nonrstr = 0
                    ## for single bus system
                    elif self.temp_nonrstr > self._settings.t_th2t:
                        self.trip_nonrstr = True
                        Kth_nonrstr = 0
                    elif self.temp_nonrstr > self._settings.t_th1t and self.temp_nonrstr <= self._settings.t_th2t:
                        Kth_nonrstr = 1 - (self.temp_nonrstr - self._settings.t_th1t)/(self._settings.t_th2t - self._settings.t_th1t)
                    # # for multiple bus system
                    # elif self.temp_nonrstr > self.thermal_threshold:
                    #     self.trip_nonrstr = True
                    #     Kth_nonrstr = 0
                    else:
                        Kth_nonrstr = 1
                else:
                    Kth_rstr = 1
                    Kth_nonrstr = 1

                pset = (Kth_rstr*p_rstrt + Kth_nonrstr*p_nonrstrt) * self.kw_rated
                qset = (Kth_rstr*q_rstrt + Kth_nonrstr*q_nonrstrt) * self.kw_rated
                if self.stall:
                    qset = (Kth_rstr*q_rstrt + Kth_nonrstr*q_nonrstrt) * self.kw_rated
                logger.debug(f"pset: {pset}")
                logger.debug(f"qset: {qset}")

                self._controlled_element.SetParameter('kw', Kthc * Kthuv * pset ) 
                self._controlled_element.SetParameter('kvar', Kthc * Kthuv * qset )
            
            self.voltage_prev = self.voltage_pu
            self.temp_rstr_prev = self.temp_rstr
            self.i2r_rstr_prev = self.i2r_rstr
            self.temp_nonrstr_prev = self.temp_nonrstr
            self.i2r_nonrstr_prev = self.i2r_nonrstr
        return 0

