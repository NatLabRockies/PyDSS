from typing import Union, Annotated

from pydantic import BaseModel, Field, model_validator

from pydss.pyControllers.enumerations import (
    CategoryI, 
    CategoryII, 
    CategoryIII, 
    PvStandard, 
    VoltageCalcModes, 
    RideThroughCategory, 
    PermissiveOperation, 
    MayTripOperation, 
    MultipleDisturbances,
    SmartControls, 
    ControlPriority, 
    VoltWattCurtailmentStrategy, 
)



class BaseControllerModel(BaseModel):
    ...
    
    
class PvVoltageRideThruModel(BaseControllerModel):
    """Data model for the PV voltage ride through controller"""
    
    kva : Annotated[
        float,
        Field(4.0, ge=0.0, description="kVA capacity of the inverter (AC-side)."),
    ] 
    max_kw: Annotated[
        float,
        Field(4.0, ge=0.0, description="kW capacity of the PV system (DC-side)."),
    ] 
    voltage_calc_mode: Annotated[
        VoltageCalcModes,
        Field(
            VoltageCalcModes.MAX, 
            description="Voltage values used to calculate Var support from the inverter (Maximum or Average)."),
    ] 
    follow_standard: Annotated[
        PvStandard,
        Field(PvStandard.IEEE_1547_2018, description="IEEE standard the inverter is following."),
    ] 
    ride_through_category : Annotated[
        RideThroughCategory,
        Field(RideThroughCategory.CATEGORY_I, description="PV ride-through category fot the inverter (see IEEE 1547-2018 std for more information)."),
    ] 
    ov_2_pu: Annotated[
        float,
        Field(CategoryI.OV2_PU.value, description="Upper bound for the over-voltage region."),
    ] 
    ov_2_ct_sec: Annotated[
        float,
        Field(CategoryI.OV2_CT_SEC.value, description="Trip duration setting if the upper bound of the over-voltage region is violated."),
    ] 
    ov_1_pu: Annotated[
        float,
        Field(CategoryI.OV1_PU.value, description="Lower bound for the over-voltage region."),
    ] 
    ov_1_ct_sec: Annotated[
        float,
        Field(CategoryI.OV1_CT_SEC.value, description="Trip duration setting if the lower bound of the over-voltage region is violated."),
    ] 
    uv_1_pu: Annotated[
        float,
        Field(CategoryI.UV1_PU.value, description="Upper bound for the under-voltage region."),
    ] 
    uv_1_ct_sec: Annotated[
        float,
        Field(CategoryI.UV1_CT_SEC.value, description="Trip duration setting if the upper bound of the under-voltage region is violated."),
    ] 
    uv_2_pu:  Annotated[
        float,
        Field(CategoryI.UV2_PU.value, description="Lower bound for the under-voltage region."),
    ]   
    uv_2_ct_sec: Annotated[
        float,
        Field(CategoryI.UV2_CT_SEC.value, description="Trip duration setting if the upper bound of the under-voltage region is violated."),
    ] 
    reconnect_deadtime_sec : Annotated[
        float,
        Field(3000.0, ge=0.0, description=""),
    ] 
    reconnect_pmax_time_sec : Annotated[
        float,
        Field(300.0, ge=0.0, description="Reconnect after a trip event. PV system will connect back once this time has elapsed and the system voltage is within bounds."),
    ] 
    permissive_operation: Annotated[
        PermissiveOperation,
        Field(PermissiveOperation.CURRENT_LIMITED, description="Defines behavior of the system within the 'permissive operation' region. (see IEEE 1547-2018 std for more information)."),
    ] 
    may_trip_operation: Annotated[
        MayTripOperation,
        Field(MayTripOperation.TRIP, description="Defines behavior of the system within the 'may trip' region. (see IEEE 1547-2018 std for more information)."),
    ] 
    multiple_disturdances: Annotated[
        MultipleDisturbances,
        Field(MultipleDisturbances.TRIP, description="Defines behavior of the system after multiple disturbances. (see IEEE 1547-2018 std for more information)."),
    ] 

    @model_validator(mode='after')
    def update_settings(self) -> 'PvVoltageRideThruModel':
        cat1 = self.ride_through_category == RideThroughCategory.CATEGORY_I
        cat2 = self.ride_through_category == RideThroughCategory.CATEGORY_II
          
        self.ov_2_pu = CategoryI.OV2_PU.value if cat1 else CategoryII.OV2_PU.value if cat2 else CategoryIII.OV2_PU.value
        self.ov_1_pu = CategoryI.OV1_PU.value if cat1 else CategoryII.OV1_PU.value if cat2 else CategoryIII.OV1_PU.value
        self.uv_2_pu = CategoryI.UV2_PU.value if cat1 else CategoryII.UV2_PU.value if cat2 else CategoryIII.UV2_PU.value
        self.uv_1_pu = CategoryI.UV1_PU.value if cat1 else CategoryII.UV1_PU.value if cat2 else CategoryIII.UV1_PU.value     
        self.ov_2_ct_sec = CategoryI.OV2_CT_SEC.value if cat1 else CategoryII.OV2_CT_SEC.value if cat2 else CategoryIII.OV2_CT_SEC.value
        self.ov_1_ct_sec = CategoryI.OV1_CT_SEC.value if cat1 else CategoryII.OV1_CT_SEC.value if cat2 else CategoryIII.OV1_CT_SEC.value
        self.uv_2_ct_sec = CategoryI.UV2_CT_SEC.value if cat1 else CategoryII.UV2_CT_SEC.value if cat2 else CategoryIII.UV2_CT_SEC.value
        self.uv_1_ct_sec = CategoryI.UV1_CT_SEC.value if cat1 else CategoryII.UV1_CT_SEC.value if cat2 else CategoryIII.UV1_CT_SEC.value
        
        return self



class PvSmartController(BaseControllerModel):
    kvar_limit: Annotated[
        float,
        Field(1.76, ge=0.0, description="kVar capacity of the PV system."),
    ] 
    pct_p_cutin: Annotated[
        float,
        Field(10.0, ge=0.0, le=100.0, description="Percentage of kVA rating of inverter. When the inverter is OFF, the power from the system must be greater than this for the inverter to turn on"),
    ] 
    pct_p_cutout: Annotated[
        float,
        Field(10.0, ge=0.0, le=100.0, description="Percentage of kVA rating of inverter. When the inverter is ON, the inverter turns OFF when the power from the array drops below this value."),
    ] 
    enable_pf_limit: Annotated[
        bool,
        Field(False, description="Enable flag to apply power factor limits on the inverter output"),
    ] 
    pf_min: Annotated[
        float,
        Field(0.95, ge=0.0, le=1.0, description="Minimum allowable powerfactor for the system. 'enable_pf_limit' should be enable for the constraint to be implemented."),
    ] 
    
class MotorStallSimpleSettings(BaseControllerModel):
    p_fault: Annotated[
        float,
        Field(3.5, ge=3.0, le=5.0, description="Active power multiplier post fault."),
    ] 
    q_fault: Annotated[
        float,
        Field(5.0, ge=3.0, le=7.0, description="Reactive power multiplier post fault."),
    ] 
    v_stall: Annotated[
        float,
        Field(0.55, ge=0.53, le=0.58, description="Per unit voltage below which the motor will stall."),
    ] 
    t_protection: Annotated[
        float,
        Field(0.95, ge=0.0, le=15.0, description="Time [sec] after stall the motor will disconnect."),
    ] 
    t_reconnect: Annotated[
        float,
        Field(6.0, ge=5.0, le=7.0, description="Time duration [sec] after which the motor will reconnect."),
    ] 
    

class MotorStallSettings(BaseControllerModel):
    t_stall:  Annotated[
        float,
        Field(0.032, description="Stall time (range) based on laboratory testing"),
    ] 
    t_restart:  Annotated[
        float,
        Field(0.300, description="Induction motor restart time is relatively short"),
    ]
    comp_lf:  Annotated[
        float,
        Field(1.000, description="Motor D real power to motor base ratio"),
    ]    
    rated_pf:  Annotated[
        float,
        Field(0.980, description="Assumed slightly inductive motors load"),
    ] 
    v_stall:  Annotated[
        float,
        Field(0.45, ge=0.40, le=0.70,  description="Stall voltage (range) based on laboratory testing"),
    ] 
    r_stall_pu:  Annotated[
        float,
        Field(0.120, description="Based on laboratory testing results of residential air-conditioners."),
    ]
    x_stall_pu:  Annotated[
        float,
        Field(0.120, description="Based on laboratory testing results of residential air-conditioners."),
    ]
    lf_adj:  Annotated[
        float,
        Field(0.0, description="Load factor adjustment to the stall voltage10"),
    ] 
    k_p1:  Annotated[
        float,
        Field(0 , description="Real power constant for running state 111"),
    ] 
    n_p1:  Annotated[
        float,
        Field(1.0, description="Real power exponent for running state 1"),
    ] 
    k_p2:  Annotated[
        float,
        Field(12.0, description="Real power constant for running state 2"),
    ] 
    n_p2:  Annotated[
        float,
        Field(3.2, description="Real power exponent for running state 2"),
    ] 
    k_q1:  Annotated[
        float,
        Field(6.0, description="Reactive power constant for running state 1"),
    ] 
    n_q1:  Annotated[
        float,
        Field(2.0, description="Reactive power exponent for running state 1"),
    ] 
    k_q2:  Annotated[
        float,
        Field(11.0, description="Reactive power constant for running state 2"),
    ] 
    n_q2:  Annotated[
        float,
        Field(2.5, description="Reactive power exponent for running state 2."),
    ] 
    v_break:  Annotated[
        float,
        Field(0.86, description="Compressor motor 'breakdown' voltage (pu)"),
    ] 
    f_rst:  Annotated[
        float,
        Field(0.2, description="Captures diversity in load; also based on testing (fraction of motors capable of restart)."),
    ] 
    v_rstrt: Annotated[
        float,
        Field(0.95, description="Reconnect when acceptable voltage met"),
    ] 
    vc_1off:  Annotated[
        float,
        Field(0.5, description="Motor D voltage at which contactors start opening, pu"),
    ] 
    vc_2off:  Annotated[
        float,
        Field(0.4, description="Motor D voltage at which all contactors are opened, pu"),
    ]
    vc_1on:  Annotated[
        float,
        Field(0.6, description="Motor D voltage at which all contactors are reclosed, pu"),
    ] 
    vc_2on:  Annotated[
        float,
        Field(0.5, description="Motor D voltage at which contactors start reclosing, pu"),
    ] 
    t_th:  Annotated[
        float,
        Field(15.0, description="Varies based on manufacturer and external factors - sensitivity analysis required"),
    ] 
    t_th1t:  Annotated[
        float,
        Field(0.7, description="Assumed tripping starting at 70% temperature"),
    ] 
    t_th2t:  Annotated[
        float,
        Field(1.9, description="Assumed all tripped at 190% temperature"),
    ] 
    f_uvr:  Annotated[
        float,
        Field(0.0, ge=0.0, le=0.10,  description="Motor D heating time constant, s"),
    ] 
    uv_tr1:  Annotated[
        float,
        Field(0.6, ge=0.45, le=0.70,  description="Motor D 1st undervoltage pick-up, pu"),
    ] 
    t_tr1:  Annotated[
        float,
        Field(0.02, ge=0.01, le=0.05,  description="Motor D 1st undervoltage trip delay, s"),
    ] 


    

class PvControllerModel(BaseControllerModel):
    control1: Annotated[
        SmartControls,
        Field(
            SmartControls.VOLT_VAR,
            title="Control1",
            description="Algorithm to run in the first control loop",
            alias="Control1",
        )]
    control2: Annotated[
        SmartControls, 
        Field(
            SmartControls.NONE,
            title="Control1",
            description="Algorithm to run in the second control loop",
            alias="Control2",
        )]  
    control3: Annotated[
        SmartControls, 
        Field(
            SmartControls.NONE,
            title="Control3",
            description="Algorithm to run in the third control loop",
            alias="Control3",
        )]
    pf: Annotated[
        float,
        Field(
            1.0,
            title="pf",
            description="Power factor for the PV system",
        )] 
    pf_min: Annotated[
        float,
        Field(
            0.8,
            title="pfMin",
            description="Minimum allowable power factor for the PV system. Applied only if enable_pf_limit is set.",
            alias="pfMin",
        )]
    pf_max: Annotated[
        float,
        Field(
            1.0,
            title="pfMax",
            description="Maximum allowable power factor for the PV system. Applied only if enable_pf_limit is set.",
            alias="pfMax",
        )]
    p_min: Annotated[
        float,
        Field(
            0.0,
            title="Pmin",
            description="TODO",
            alias="Pmin",
        )]
    p_max:Annotated[
        float,
        Field(
            1.0,
            title="Pmax",
            description="TODO",
            alias="Pmax",
        )]
    u_min: Annotated[
        float,
        Field(
            0.94,
            title="uMin",
            description="Per unit voltage value at which inverter produces maximum vars. (volt / var algorithm).",
            alias="uMin",
        )]
    u_db_min: Annotated[
        float,
        Field(
            0.97,
            title="uDbMin",
            description="Lower bound for the voltage deadband [per unit]. Inverter will not produce or consume vars within these bands (volt / var algorithm).",
            alias="uDbMin",
        )]
    u_db_max: Annotated[
        float,
        Field(
            1.03,
            title="uDbMax",
            description="Upper bound for the voltage deadband [per unit]. Inverter will not produce or consume vars within these bands (volt / var algorithm).",
            alias="uDbMax",
        )]
    u_max: Annotated[
        float,
        Field(
            1.06,
            title="uMax",
            description="Per unit voltage value at which inverter consumes maximum vars (volt / var algorithm).",
            alias="uMax",
        )]
    q_lim_pu: Annotated[
        float,
        Field(
            0.44,
            title="QlimPU",
            description="Inverter reactive power limit [per unit] for the volt / var algorithm.",
            alias="QlimPU",
        )]
    pf_lim: Annotated[
        float,
        Field(
            0.9,
            title="PFlim",
            description="Inverter power factor limit. Applied only if enable_pf_limit is set.",
            alias="PFlim",
        )]
    enable_pf_limit: Annotated[
        bool,
        Field(
            False,
            title="EnablePFLimit",
            description="Flag to enable / disable power factor limits on the inverter",
            alias="Enable PF limit",
        )]
    u_min_c: Annotated[
        float,
        Field(
            1.06,
            title="uMinC",
            description="Lower voltage bound [per unit] for the volt / watt algorithm",
            alias="uMinC",
        )]
    u_max_c: Annotated[
        float,
        Field(
            1.1,
            title="uMaxC",
            description="Upper voltage bound [per unit] for the volt / watt algorithm",
            alias="uMaxC",
        )]
    p_min_vw: Annotated[
        float,
        Field(
            10.0,
            title="PminVW",
            description="Lower bound for the inveter active power output for the volt / watt algorithm",
            alias="PminVW",
        )]
    vw_type: Annotated[
        VoltWattCurtailmentStrategy,
        Field(
            VoltWattCurtailmentStrategy.RAETED_POWER,
            title="VWtype",
            description="volt / watt algorithm to be implemented on rated or available power",
            alias="VWtype",
        )]
    percent_p_cutin: Annotated[
        float,
        Field(
            10.0,
            title="PCutin",
            description="Percentage cut-in power -- Percentage of kVA rating of inverter. When the inverter is OFF, the power from the array must be greater than this for the inverter to turn on.",
            alias="%PCutin",
        )]
    percent_p_cutout: Annotated[
        float,
        Field(
            10.0,
            title="%PCutout",
            description="Percentage cut-out power -- Percentage of kVA rating of inverter. When the inverter is ON, the inverter turns OFF when the power from the array drops below this value.",
            alias="%PCutout",
        )]
    efficiency: Annotated[
        float,
        Field(
            100.0,
            title="Efficiency",
            description="Efficieny of the inverter system",
            alias="Efficiency",
        )]
    priority: Annotated[
        ControlPriority,
        Field(
            ControlPriority.VAR,
            title="Priority",
            description="Set export priority for active power or reactive power",
            alias="Priority",
        )]
    damp_coef: Annotated[
        float,
        Field(
            0.8,
            title="DampCoef",
            description="Damping cooefficient for the convergence algorithm",
            alias="DampCoef",
        )]
    voltage_calc_mode: Annotated[
        VoltageCalcModes,
        Field(
            VoltageCalcModes.MAX, 
            description="Voltage values used for calculations."),
    ] 