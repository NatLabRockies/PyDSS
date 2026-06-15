#QSTS Model for Dynamic Voltage Support from Inverter Based Resources 
'''
author: Erik Pohl
Version: 2.0
'''

from pydss.pyControllers.pyControllerAbstract import ControllerAbstract
import matplotlib.pyplot as plt
import scipy.signal as signal
import numpy as np
import math
import statistics as stats

class DynamicVoltageSupport(ControllerAbstract):
    """The controller implements Dynamic Voltage Support for Generator objects as loosely defined in 1547-2018 as "rapid reactive power exchanges during voltage excursions." 
        Subclass of the :class:`PyDSS.pyControllers. pyControllerAbstract.ControllerAbstract` abstract class.

        :param PvObj: A :class:`PyDSS.dssElement.dssElement` object that wraps around an OpenDSS 'Generator' element
        :type PvObj: class:`PyDSS.dssElement.dssElement`
        :param Settings: A dictionary that defines the settings for the DynamicVoltageSupport Controller.
        :type Settings: dict
        :param dssInstance: An :class:`opendssdirect` instance
        :type dssInstance: :class:`opendssdirect`
        :param ElmObjectList: Dictionary of all dssElement, dssBus and dssCircuit objects
        :type ElmObjectList: dict
        :param dssSolver: An instance of one of the classed defined in :mod:`PyDSS.SolveMode`.
        :type dssSolver: :mod:`PyDSS.SolveMode`
        :raises: AssertionError if 'PvObj' is not a wrapped OpenDSS Generator element
        :raises: AssertionErrot if 'PvObj' is not a 3ph Generator element

    """
    def __init__(self, PvObj, Settings, dssInstance, ElmObjectList, dssSolver):
        super(DynamicVoltageSupport, self).__init__(PvObj, Settings, dssInstance, ElmObjectList, dssSolver)
        self._class, self._name = PvObj.GetInfo()
        assert (self._class.lower()=='generator'), 'DynamicVoltageSupport works only with an OpenDSS generator element'
        self.name = "Controller-{}-{}".format(self._class, self._name)
        self._ControlledElm = PvObj
        self.__Settings = Settings
        self.__dssSolver = dssSolver
        self.gen_Phases = float(PvObj.GetParameter('phases'))
        assert(int(self.gen_Phases) == 3), 'DynamicVoltageSupport works only with a 3ph OpenDSS generator element. {ph} ph generator object was used.'.format(
            ph=int(self.gen_Phases)
            )

        # GET GENERATOR ORIGINAL OBJECT PARAMETERS
        # These will be used when resetting the generator behavior in post-fault periods
        self.gen_BaseKV = float(PvObj.GetParameter('kv'))
        self.gen_Srated = float(PvObj.GetParameter('kVA'))
        self.gen_Kw = float(PvObj.GetParameter('kw'))
        self.gen_Kvar = float(PvObj.GetParameter('kvar'))
        self.prev_kvar=self.gen_Kvar
        self.gen_Srated_adjusted=self.gen_Srated
        self.kva_calc=math.sqrt((self.gen_Kw**2)+(self.gen_Kvar**2))
        
        #GET TOML USER-DEFINED SETTINGS
        self.Trv=self.__Settings['Trv'] #time-constant for voltage transducer
        self.Tinv=self.__Settings['Tinv'] #time-constant for inverter controller
        self.dbd1=self.__Settings['dbd1'] #single-sided lower deadband (delta V p.u)
        self.dbd2=self.__Settings['dbd2'] #single-sided upper deadband (delta V p.u)
        self.Kqv=self.__Settings['Kqv'] #proportional gain constant
        self.iqh1=self.__Settings['iqh1'] #current limit for injection (p.u)
        self.kvarmax_pu=self.__Settings['kvar_max'] #max kvar injection (p.u) (positive number)
        self.kvarmin_pu=self.__Settings['kvar_min'] #max kvar absorption (p.u) (negative number)
        self.post_fault_reset=self.__Settings['post_fault_reset'] #time (s) after fault before gen provides more support
        self.capacitive_support=self.__Settings['capacitive_support'] #bool indicating if gen will provide capacitive support
        self.inductive_support=self.__Settings['inductive_support'] #bool indicating if gen will provide inductive support
        self.current_limited_error_tolerance=self.__Settings['current_limited_error_tolerance'] #error tolerance (%) when evaluating current limit adherance
        self.overvoltage_kva_limited=self.__Settings['overvoltage_kva_limited'] #bool indicating if gen is kva limited
        self.use_with_voltage_ride_through=self.__Settings['Use with Voltage Ride Through'] #bool indicating if DVS controller is used concurrently with VRT controller

        #CALC KVAR LIMITS
        self.kvarmax=self.kvarmax_pu*self.gen_Srated
        self.kvarmin=self.kvarmin_pu*self.gen_Srated

        #RESET GENERATOR MODEL
        self.Model = int(PvObj.SetParameter('model',1)) #set generator model to model 1 to allow for PyDSS-controller current limit
        self.vminpu = float(PvObj.SetParameter('Vminpu',0)) #using arbitrarily wide voltages so that it is always constant kW constant kVAR
        self.vmaxpu = float(PvObj.SetParameter('Vmaxpu',2)) #using arbitrarily wide voltages so that it is always constant kW constant kVAR

        #SET GENERATOR CURRENT LIMITS
        self.gen_imax_per_phase=self.iqh1*(self.gen_Srated/(self.gen_BaseKV*math.sqrt(3)))

        #SET UP VOLTAGE TRANSDUCER TRANSFER FUNCTION 
        self.V_filter_transfer_function = signal.TransferFunction([1], [self.Trv, 1])

        #SET UP INVERTER CONTROLLER TRANSFER FUNCTION
        self.inv_control_transfer_function=signal.TransferFunction([1],[self.Tinv, 1])
        
        #GET/SET INITIAL CONDITIONS
        self.dt = dssSolver.GetStepResolutionSeconds()
        ave_v_pu = stats.mean(self._ControlledElm.sBus[0].GetVariable("puVmagAngle")[0:-2:2]) #using mean phase voltages
        self.T=[0,self.dt]
        self.V=[ave_v_pu,ave_v_pu]
        self.V_filt=self.V[-1]
        self.Vref=ave_v_pu 
        self.V_err=0
        self.inv_control_kw=np.array([self.gen_Kw,self.gen_Kw])
        self.inv_control_kvar=np.array([self.gen_Kvar,self.gen_Kvar])
        self.inv_out_kw_prev=self.gen_Kw*self.Tinv #spin up the inverter controller
        self.inv_out_kvar_prev=self.gen_Kvar*self.Tinv #spin up the inverter controller
        self.v_out_prev=ave_v_pu*self.Trv #spin up the voltage transducer
        self.Fault_present=False
        self.fault_reset_start=0
        self.first_step=True
        self.time_advance=False
        return
    
    def Name(self):
        return self.name

    def ControlledElement(self):
        return "{}.{}".format(self._class, self._name)

    def debugInfo(self):
        return 
    
    def Voltage_Transducer(self,ave_v_pu):
        self.V=np.array([self.V[-1],ave_v_pu]) #update input array with the current time-step voltage
        _,self.V_filt,vout=signal.lsim(self.V_filter_transfer_function,self.V,self.T,X0=self.v_out_prev) #run it through our voltage transducer to get response
        self.v_out_prev=vout[-1] #record evolution of state vector for next step initial condition
        
        #CALCULATE V_ERROR
        self.V_err=self.V_filt[-1]-self.Vref #positive V_err = overvoltage, negative V_err = undervoltage
        return 
    
    def Inverter_Controller(self,kw_kvar:str,new_setting):
        if kw_kvar == 'kw': #if we are controlling kw
            self.inv_control_kw=np.array([self.kw_setting_prev,new_setting]) # set to last step kvar and the desired next step
            _,self.inv_control_filt_kw,inv_out_kw=signal.lsim(self.inv_control_transfer_function,self.inv_control_kw,self.T,X0=self.inv_out_kw_prev) #run through our transfer function to get response
            self.inv_out_kw_prev=inv_out_kw[-1] #record evolution of state vector for next step initial conditioN
        else: #if we are controlling kvar
            self.inv_control_kvar=np.array([self.kvar_setting_prev,new_setting]) # set to last step kvar and the desired next step
            _,self.inv_control_filt_kvar,inv_out_kvar=signal.lsim(self.inv_control_transfer_function,self.inv_control_kvar,self.T,X0=self.inv_out_kvar_prev) #run through our transfer function to get response
            self.inv_out_kvar_prev=inv_out_kvar[-1] #record evolution of state vector for next step initial condition
        return
    
    def Restore_Output(self):
        new_kvar=self.gen_Kvar #set new_kvar to original q value
        
        #APPLY TRANSFER FUNCTION TO INVERTER CONTROLLER TO LIMIT SPEED OF KVAR CHANGES
        self.Inverter_Controller('kvar',new_kvar)
        new_kw=math.sqrt((self.kva_calc**2)-(self.inv_control_filt_kvar[-1]**2)) #based on the response change in kvar, we calculate the desired kw

        #APPLY TRANSFER FUNCTION TO INVERTER CONTROLLER TO LIMIT SPEED OF KW CHANGES
        self.Inverter_Controller('kw',new_kw)
        if round(self.inv_control_filt_kw[-1]) == round(self.gen_Kw) and round(self.inv_control_filt_kvar[-1]) == round(self.gen_Kvar): #once we get close to original value 
            self.Fault_present = False #end the faulted state
            self.Vref=self.V_filt[-1] #reset the vref when not in a fault state
            new_step_kw=self.gen_Kw #set generator kw to exactly the original value
            new_step_kvar=self.gen_Kvar #set generator kvar to exactly the original value
            error=0
        else: #if not close eneough, we will move to the next time step while maintaining a faulted state
            new_step_kw=self.inv_control_filt_kw[-1]
            new_step_kvar=self.inv_control_filt_kvar[-1]
            error=0

        return new_step_kw,new_step_kvar,error
    
    def Fault_Support(self):
        if self.fault_reset_start == 0 or (self.T[-1]-self.fault_reset_start) >= self.post_fault_reset: #check if we have exceeded our reset timer
            self.Fault_present=True
            self.fault_reset_start=0

            #UNDERVOLTAGE CONDITION
            if self.V_err <= self.dbd1: 
                if self.capacitive_support: #check if user wants DER to provide capacitive support
                    if self.kvar_setting_prev < self.kvarmax: 
                        new_kvar=self.kvar_setting_prev+(-self.V_err*self.Kqv) #calc new kvar value using gain constant
                        if new_kvar > self.kvarmax: #if it exceeds user-defined kvarmax
                            new_kvar=self.kvarmax #set to kvar_max
                    else:
                        new_kvar=self.kvarmax
                else:
                    new_kvar=self.gen_Kvar #if no capacitive support, keep kvar value as defined in dss files
                    
                self.gen_Srated_adjusted=self.gen_Srated

            #OVERVOLTAGE CONDITION
            else:
                if self.inductive_support and self.kvar_setting_prev > self.kvarmin:
                    new_kvar=self.kvar_setting_prev+(-self.V_err*self.Kqv)
                    if new_kvar < self.kvarmin:
                        new_kvar=self.kvarmin
                elif self.inductive_support:
                    new_kvar=self.kvarmin
                else:
                    new_kvar=self.gen_Kvar

                self.gen_Srated_adjusted=self.gen_Srated

            #APPLY TRANSFER FUNCTION TO INVERTER CONTROLLER TO LIMIT SPEED OF KVAR CHANGES
            self.Inverter_Controller('kvar',new_kvar) #once we calculate the desired kvar response, we run it through out inverter controller to get the response
            
            if self.kw_setting_prev==0: #if not generating active power in previous step, keep this the same, because we can't curtail any more.
                new_kw=self.kw_setting_prev
            else: # else, we will assign kw value based on the desired kvar value (i.e will curtail if needed)
                new_kw=math.sqrt(((self.gen_Srated_adjusted*self.iqh1)**2)-(self.inv_control_filt_kvar[-1]**2)) #calc new kw value using new kvar and the nameplate rating of gen.
            #APPLY TRANSFER FUNCTION TO INVERTER CONTROLLER TO LIMIT SPEED OF KW CHANGES
            self.Inverter_Controller('kw',new_kw)

            new_step_kw=self.inv_control_filt_kw[-1]
            new_step_kvar=self.inv_control_filt_kvar[-1]
            error=100#force another iteration to enforce a current limit when a fault is present and we are altering generator values
        else: #if we haven't exceeded our reset timer, keep everything the same
            self.Fault_present=False
            self.Vref=self.V_filt[-1]#reset Vref to the current timestep voltage
            new_step_kw=self.gen_Kw
            new_step_kvar=self.gen_Kvar
            error=0
        return new_step_kw, new_step_kvar, error
    
    def kVA_Limiter(self):
        if self.kw_setting_prev>0:# if there active power generation
            new_kw=math.sqrt((self.gen_Srated_adjusted**2)-(self.kvar_setting_prev**2))#calc new kw setting based on current kvar setting
            if new_kw>0: #if the new kw settings does not cause kw to go negative
                new_step_kw=new_kw
                new_step_kvar=self.kvar_setting_prev
            else: #otherwise just set kw to 0
                new_step_kw=0
                new_step_kvar=self.kvar_setting_prev
        else: #if kw setting is already 0, we need to reduce kVAR
            new_kvar=math.sqrt((self.gen_Srated_adjusted**2)-(self.kw_setting_prev**2))
            new_step_kw=self.kw_setting_prev #no need to calculate a new kW setting
            new_step_kvar=new_kvar
        error=100#force another iteration to check if we successfully enforced the kVA limit within tolerances
        return new_step_kw, new_step_kvar, error
    
    def Current_Limiter(self,iter_v):
        adjusted_kva=self.gen_imax_per_phase*(iter_v*math.sqrt(3)) #get the kva limit for the current timestep at the current voltage
        if self.kw_setting_prev>0: # if there active power generation
            if self.kvar_setting_prev>adjusted_kva:
                new_step_kw=0
                new_step_kvar=self.kvar_setting_prev
            else:
                new_step_kw=math.sqrt((adjusted_kva**2)-(self.kvar_setting_prev**2))#calc new kw setting based on current kvar setting
                new_step_kvar=self.kvar_setting_prev
            # if new_kw>0: #if the new kw settings does not cause kw to go negative
            #     new_step_kw=new_kw
            #     new_step_kvar=self.kvar_setting_prev
            # else: #otherwise just set kw to 0
            #     new_step_kw=0
            #     new_step_kvar=self.kvar_setting_prev
        else: #if kw setting is already 0
            new_kvar=math.sqrt((adjusted_kva**2)-(self.kw_setting_prev**2))
            new_step_kw=self.kw_setting_prev #no need to calculate a new kW setting
            new_step_kvar=new_kvar
        error=100 #force another iteration to check if we successfully enforced the current limit within tolerances
        return new_step_kw, new_step_kvar, error

    def Update(self, Priority, Time, UpdateResults):
        error=0
        
        if Priority == 1: 
            
            #GET PREVIOUS STEP GENERATOR SETTINGS. THESE WILL GET UPDATED IF WARRANTED. 
            self.kw_setting_prev=float(self._ControlledElm.GetParameter('kw'))
            self.kvar_setting_prev=float(self._ControlledElm.GetParameter('kvar'))
            
            #UPDATE TIME ARRAY
            t=self.__dssSolver.GetTotalSeconds()
            if t > self.T[-1]: #Check if this is a new timestep or a second control iteration
                self.time_advance=True
                self.T = np.array([self.T[-1],t]) #update time array
            else:
                self.time_advance=False
            
            #IF USING DVS WITH VRT WE WILL TRACK GENERATOR STATUS (1.0 = TRIPPED, 0.0 = IN-SERVICE)
            if self.use_with_voltage_ride_through: 
                gen_trip_status=float(self._ControlledElm.GetParameter('Class')) #VRT controller uses opendss 'class' parameter to indicate trip status
            else:
                gen_trip_status=0.0 #if not using with VRT, set trip status to 0.0 (in-service) all the time. 
            #IF NOT USING WITH VRT OR IF USING WITH VRT AND GENERATOR IS NOT TRIPPED, THEN WE WILL EVALUATE IF WE NEED TO MAKE CHANGES TO GENERATOR KW/KVAR
            if not self.use_with_voltage_ride_through or (self.use_with_voltage_ride_through and not bool(gen_trip_status)): 
                #COLLECT KEY QUANTITIES
                ave_v_pu = stats.mean(self._ControlledElm.sBus[0].GetVariable("puVmagAngle")[0:-2:2]) 
                
                #IF THERE IS A TIME ADVANCE, REEVALUATE GENERATOR SETTINGS
                if self.time_advance or self.first_step: 
                    self.first_step=False
                    #CALCULATE FILTERED VOLTAGE USING TRANSFER FUNCTION AT EACH NEW TIMESTEP
                    self.Voltage_Transducer(ave_v_pu)

                    #GET CURRENT STEP OUTPUT FROM GENERATOR
                    iter_q=-1*sum(self._ControlledElm.GetVariable('Powers')[1:-1:2])
                    iter_p=-1*sum(self._ControlledElm.GetVariable('Powers')[0:-1:2])

                    #NO_FAULT CONDITION: if V_err within of user-defined deadband
                    if self.V_err > self.dbd1 and self.V_err < self.dbd2: 
                        if self.Fault_present: #if transitioning from a faulted state to an unfaulted state, start user-defined reset timer
                            self.fault_reset_start=self.T[-1]
                            # self.Fault_present=False
                            new_step_kw,new_step_kvar,error=self.Restore_Output() #start restoring output to pre-fault conditions
                        else: #if not transitioning from faulted state to unfaulted state, keep everything the same
                            self.Inverter_Controller('kw',self.gen_Kw)
                            self.Inverter_Controller('kvar',self.gen_Kvar)
                            # new_step_kw=self.inv_control_filt_kw[-1]
                            # new_step_kvar=self.inv_control_filt_kvar[-1]
                            new_step_kw=self.gen_Kw
                            new_step_kvar=self.gen_Kvar
                            error=0

                    #FAULT CONDITION: V_err is outside of user-defined deadband
                    else: 
                        new_step_kw,new_step_kvar,error=self.Fault_Support() #provide fault support through DVS

                else: #RERUNNING TIMESTEP AGAIN AND ENFORCING CURRENT OR KVA LIMIT AT THE CURRENT VOLTAGE LEVEL
                    #GET CURRENT ITERATION KEY QUANTITIES
                    iter_curr=max(self._ControlledElm.GetVariable('CurrentsMagAng')[0:-2:2])
                    iter_p=-1*sum(self._ControlledElm.GetVariable('Powers')[0:-1:2])
                    iter_q=-1*sum(self._ControlledElm.GetVariable('Powers')[1:-1:2])
                    iter_v=stats.mean(self._ControlledElm.sBus[0].GetVariable("puVmagAngle")[0:-2:2])*(self.gen_BaseKV)
                    
                    #CALCULATE IF WE OVERSHOT OR UNDERSHOT OUR CURRENT LIMIT AT THE CURRENT VOLTAGE LEVEL
                    curr_over_under=iter_curr-self.gen_imax_per_phase
                    curr_over_under_pct=curr_over_under/self.gen_imax_per_phase

                    #CALCULATE IF WE OVERSHOT OUR GENERATOR KVA NAMEPLATE
                    kva_overshoot=(math.sqrt((iter_p**2)+(iter_q**2)))-self.gen_Srated
                    kva_overshoot_pct=kva_overshoot/self.gen_Srated
                    
                    #READJUST QUANTITIES AS NEEDED
                    if self.Fault_present: #Only adjust quantities if there is a fault present and we are changing generator behavior
                        if self.overvoltage_kva_limited and kva_overshoot_pct>self.current_limited_error_tolerance: #if user wants to enforce a kva limit and we have exceeded that
                            new_step_kw, new_step_kvar, error=self.kVA_Limiter() #run the kVA limiter
                        elif abs(curr_over_under_pct)>self.current_limited_error_tolerance:#if we haven't exceeded our kva limit, check if we have exceeded our current limit
                            if self.overvoltage_kva_limited and curr_over_under_pct<0:# if the DER is being kva limited, we allow for DER to undershoot its current limit
                                new_step_kw=self.kw_setting_prev
                                new_step_kvar=self.kvar_setting_prev
                                error=0
                            else: #if it is not kva limited, then we will enfore only the current limit
                                new_step_kw, new_step_kvar, error=self.Current_Limiter(iter_v) #run the current-limiter
                        else:
                            new_step_kw=self.kw_setting_prev
                            new_step_kvar=self.kvar_setting_prev
                            error=0
                    else:
                        new_step_kw=self.kw_setting_prev
                        new_step_kvar=self.kvar_setting_prev
                        error=0
            else: #if the generator is in a tripped state (when using with VRT controller) then keep kw and kvar at 0
                new_step_kw=0
                new_step_kvar=0
                error=0
            #CHANGE GENERATOR SETTINGS
            self._ControlledElm.SetParameter('kw', new_step_kw)
            self._ControlledElm.SetParameter('kvar', new_step_kvar)

        else:
            error=0
        return error 
