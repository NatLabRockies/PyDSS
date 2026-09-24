from enum import Enum

class VoltageCalcModes(str, Enum):
    """
    Voltage calculation modes for the controller
    
    **MAX** - *The the maximum voltage from the available phases as the contoller input*
    
    **AVG** - *The the average voltage from the available phases as the contoller input*
    
    **MIN** - *The the minimum voltage from the available phases as the contoller input*
    
    **A** - *The voltage from phase A as the contoller input*
    
    **B** - *The voltage from phase B as the contoller input*
    
    **C** - *The voltage from phase C as the contoller input*
    """
    MAX = "Max"
    AVG = "Avg"
    MIN = "Min"
    A = "1"
    B = "2"
    C = "3"

class PvStandard(str, Enum):
    """
    PV standards for the controller
    
    **IEEE_1547_2003** - *For legacy PV systems, use the IEEE 1574-2003 standard*
    
    **IEEE_1547_2018** - *For legacy PV systems with smart controls, use the IEEE 1574-2018 standard*
    """
    IEEE_1547_2003 = "1547-2003" 
    IEEE_1547_2018 = "1547-2018"

class RideThroughCategory(str, Enum):
    """
    PV ride-through catregories
    
    **CATEGORY_I**  - *Intended to meet minimum Bulk EPS reliability needs and to be achievable by all DER technologies, including rotating machines*
    
    **CATEGORY_II**  - *Designed to align with the requirements in NERC PRC-024-2*
    
    **CATEGORY_III** - *Designed to meet the needs of low-inertia or highly-penetrated grids*
    """
    CATEGORY_I = "Category I"
    CATEGORY_II = "Category II" 
    CATEGORY_III = "Category III" 

class PermissiveOperation(str, Enum):
    """
    Possible behaviors for permissive operation
    
    **CURRENT_LIMITED** - *Current injection into the grid is limited by the inverter during low or high voltage conditions outside the continuous operating range*
    
    **MOMENTARY_SUCESSION** - *No current is injected into the grid by the inverter during low or high voltage conditions outside the continuous operating range*
    """
    CURRENT_LIMITED = "Current limited"
    MOMENTARY_SUCESSION = "Momentary sucession"

class MayTripOperation(str, Enum):
    """
    Possible behaviors for my trip region
    
    **TRIP** - *PV system disconnects from the grid. Can not reconnect for atleast 300 seconds.*
    
    **PERMISSIVE_OPERATION** - *Option for the DER to either continue to exchange current with or to cease toenergize an EPS*
    """
    TRIP = "Trip" 
    PERMISSIVE_OPERATION ="Permissive operation" 
    
class MultipleDisturbances(str, Enum):
    """
    Possible behaviors for multiple disturbamces
    
    **TRIP** - *PV system disconnects from the grid. Can not reconnect for atleast 300 seconds.*
    
    **PERMISSIVE_OPERATION** - *Option for the DER to either continue to exchange current with or to cease toenergize an EPS*
    """
    TRIP = "Trip" 
    PERMISSIVE_OPERATION = "Permissive operation" 
    
class CategoryI(float, Enum):
    """
    Variable defination for Category I
    
    **OV2_PU** - *Upper bound for the over-voltage region*
     
    **OV2_CT_SEC** - *Trip time if voltage exceeds OV2_PU (seconds)*
    
    **OV1_PU** - *Lower bound for the over-voltage region* 
    
    **OV1_CT_SEC** - *Trip time if voltage exceeds OV1_CT_SEC (seconds)*
    
    **UV1_PU** - *Upper bound for the under-voltage region* 
    
    **UV1_CT_SEC** - *Trip time if voltage is less than UV1_PU (seconds)*
    
    **UV2_PU** - *Lower bound for the under-voltage region*
    
    **UV2_CT_SEC** - *Trip time if voltage is less than UV1_PU (seconds)*
    """
    OV2_PU = 1.2 
    OV2_CT_SEC = 0.16
    OV1_PU = 1.1
    OV1_CT_SEC = 2.0
    UV1_PU = 0.7
    UV1_CT_SEC = 2.0
    UV2_PU = 0.45
    UV2_CT_SEC = 0.16

class CategoryII(float, Enum):
    """
    Variable defination for Category II
    
    **OV2_PU** - *Upper bound for the over-voltage region*
     
    **OV2_CT_SEC** - *Trip time if voltage exceeds OV2_PU (seconds)*
    
    **OV1_PU** - *Lower bound for the over-voltage region* 
    
    **OV1_CT_SEC** - *Trip time if voltage exceeds OV1_CT_SEC (seconds)*
    
    **UV1_PU** - *Upper bound for the under-voltage region* 
    
    **UV1_CT_SEC** - *Trip time if voltage is less than UV1_PU (seconds)*
    
    **UV2_PU** - *Lower bound for the under-voltage region*
    
    **UV2_CT_SEC** - *Trip time if voltage is less than UV1_PU (seconds)*
    """
    OV2_PU = 1.2
    OV2_CT_SEC = 0.16
    OV1_PU = 1.1
    OV1_CT_SEC = 2.0
    UV1_PU = 0.7
    UV1_CT_SEC = 10.0
    UV2_PU = 0.45
    UV2_CT_SEC = 0.16

class CategoryIII(float, Enum):
    """
    Variable defination for Category III
    
    **OV2_PU** - *Upper bound for the over-voltage region*
     
    **OV2_CT_SEC** - *Trip time if voltage exceeds OV2_PU (seconds)*
    
    **OV1_PU** - *Lower bound for the over-voltage region* 
    
    **OV1_CT_SEC** - *Trip time if voltage exceeds OV1_CT_SEC (seconds)*
    
    **UV1_PU** - *Upper bound for the under-voltage region* 
    
    **UV1_CT_SEC** - *Trip time if voltage is less than UV1_PU (seconds)*
    
    **UV2_PU** - *Lower bound for the under-voltage region*
    
    **UV2_CT_SEC** - *Trip time if voltage is less than UV1_PU (seconds)*
    """
    OV2_PU = 1.2
    OV2_CT_SEC = 0.16
    OV1_PU = 1.1
    OV1_CT_SEC = 13.0
    UV1_PU = 0.88
    UV1_CT_SEC = 21.0
    UV2_PU = 0.5
    UV2_CT_SEC = 2.0

class SmartControls(str, Enum):
    """
    Supported smart control algorithms
    
    **NONE** - *No contol algorithm*
     
    **CONSTANT_POWER_FACTOR** - *Constant power factor implmentation*
    
    **VARIABLE_POWER_FACTOR** - *Variable power factor implmentation* 
    
    **VOLT_VAR** - *Volt / Var algorithm implementation*
    
    **VOLT_WATT** - *Volt / Watt algorithm implementation* 
    
    **TRIP** - *Over voltage trip implementation*
    
    """
    
    NONE = 'None'           
    CONSTANT_POWER_FACTOR ='cpf'            
    VARIABLE_POWER_FACTOR ='vpf'            
    VOLT_VAR ='VVar'           
    VOLT_WATT ='vwatt'             
    TRIP = 'trip'
    
class VoltWattCurtailmentStrategy(str, Enum):
    """
    Curtailment strategy for volt / watt algorithm
    
    **AVAILABLE_POWER** - *Curtailment is based on available power of the inverter*
     
    **RAETED_POWER** - *Curtailment is based on rated power of the inverter*
        
    """
    
    AVAILABLE_POWER = 'Available Power'           
    RAETED_POWER ='Rated Power' 
