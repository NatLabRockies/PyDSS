from ipaddress import v4_int_to_packed
from  pydss.pyControllers.pyControllerAbstract import ControllerAbstract
from shapely.geometry import MultiPoint, Polygon, Point, MultiPolygon
from shapely.ops import triangulate, unary_union
import matplotlib.pyplot as plt
import datetime
import math
import os
import pdb

class PvFrequencyRideThru(ControllerAbstract):
    """Implementation of IEEE1547-2003 and IEEE1547-2018 frequency ride-through standards using the OpenDSS Generator model. Subclass of the :class:`pydss.pyControllers.pyControllerAbstract.ControllerAbstract` abstract class.

            :param PvObj: A :class:`pydss.dssElement.dssElement` object that wraps around an OpenDSS 'Generator' element
            :type FaultObj: class:`pydss.dssElement.dssElement`
            :param Settings: A dictionary that defines the settings for the PvController.
            :type Settings: dict
            :param dssInstance: An :class:`opendssdirect` instance
            :type dssInstance: :class:`opendssdirect`
            :param ElmObjectList: Dictionary of all dssElement, dssBus and dssCircuit objects
            :type ElmObjectList: dict
            :param dssSolver: An instance of one of the classed defined in :mod:`pydss.SolveMode`.
            :type dssSolver: :mod:`pydss.SolveMode`
            :raises: AssertionError if 'PvObj' is not a wrapped OpenDSS Generator element

    """

    def __init__(self, PvObj, Settings, dssInstance, ElmObjectList, dssSolver):
        super(PvFrequencyRideThru, self).__init__(PvObj, Settings, dssInstance, ElmObjectList, dssSolver)

        self.TimeChange = False
        self.Time = (-1, 0)

        self.oldPcalc = 0
        self.oldQcalc = 0
        self.Qpvpu = 0
        self. __vDisconnected = False
        self.__pDisconnected = False

        self._ElmObjectList = ElmObjectList
        self.ControlDict = {
            'None': lambda: 0,
        }

        self._ControlledElm = PvObj
        self.__ElmObjectList = ElmObjectList
        self.__dssInstance = dssInstance
        self.__dssSolver = dssSolver
        self.__Settings = Settings

        self.Class, self.Name = self._ControlledElm.GetInfo()
        assert (self.Class.lower() == 'generator'), 'PvControllerGen works only with an OpenDSS Generator element'
        self.__Name = 'pyCont_' + self.Class + '_' + self.Name
        if '_' in self.Name:
            self.Phase = self.Name.split('_')[1]
        else:
            self.Phase = None

        # Initializing the model
        PvObj.SetParameter('kvar', 0)
        self.__Srated = float(PvObj.SetParameter('kva', Settings['kVA']))
        self.__Prated = float(PvObj.SetParameter('kW', Settings['maxKW']))
        self.__minQ = float(PvObj.SetParameter('minkvar', -Settings['KvarLimit']))
        self.__maxQ = float(PvObj.SetParameter('maxkvar', Settings['KvarLimit']))

        # MISC settings
        self.__cutin = Settings['%PCutin']
        self.__cutout = Settings['%PCutout']
        self.__trip_deadtime_sec = Settings['Reconnect deadtime - sec']
        self.__Time_to_Pmax_sec = Settings['Reconnect Pmax time - sec']
        self.__Prated = Settings['maxKW']
        self.__priority = Settings['Priority']
        self.__enablePFlimit = Settings['Enable PF limit']
        self.__minPF = Settings['pfMin']
        self.__UcalcMode = Settings['UcalcMode']
        # initialize deadtimes and other variables
        self.__initializeRideThroughSettings()
        # self.__rVs, self.__rTs = self.__CreateOperationRegions()
        self.__CreateOperationRegions()
        # For debugging only
        self.useAvgFrequency = True
        cycleAvg = 5 #same for voltage and frequency.  #see Table 3 of 1547-2018. Measurement window for frequency is 5 cycles
        freq = dssSolver.getFrequency()
        step = dssSolver.GetStepSizeSec()
        hist_size = math.ceil(cycleAvg / (step * freq))
        self.frequency = [60.0 for i in range(hist_size)]
        self.reactive_power = [0.0 for i in range(hist_size)]
        self.__VoltVioM = False
        self.__VoltVioP = False
        
        self.region = [3, 3, 3]

        self.frequency_hist = []
        self.power_hist = []
        self.timer_hist = []
        self.timer_act_hist = []
        
        
        self.u_ang = self._ControlledElm.GetVariable('VoltagesMagAng')[1::2][0]
        self.df = 0
        self.freq_hist = []
        return

    def Name(self):
        return self.__Name

    def ControlledElement(self):
        return "{}.{}".format(self.Class, self.Name)

    def debugInfo(self):
        return [self.__Settings['Control{}'.format(i+1)] for i in range(3)]

    def __initializeRideThroughSettings(self):
        self.f_temp = 58.5
        self.__isConnected = True
        self.__Plimit = self.__Prated
        self.__CutoffTime = self.__dssSolver.GetDateTime()
        self.__ReconnStartTime = self.__dssSolver.GetDateTime() - datetime.timedelta(
            seconds=int(self.__Time_to_Pmax_sec))

        self.__TrippedPmaxDelay = 0
        self.__NormOper = True
        self.__NormOperStartTime = self.__dssSolver.GetDateTime()
        self.__fViolationtime = 99999
        self.__TrippedStartTime = self.__dssSolver.GetDateTime()
        self.__TrippedDeadtime = 0
        self.__faultCounter = 0
        self.__isinContinuousRegion = True
        self.__FaultwindowClearingStartTime = self.__dssSolver.GetDateTime()
        self.__continuous_f_upper = 61.2
        self.__continuous_f_lower = 58.8

        return

    def __CreateOperationRegions(self):
        fMaxTheo = 100
        tMax = 1e10
        # #deprecated...
        # V = [1.10, 0.88, 0.5, 1.2, 1.2, 1.2, 0.0, 0.0]
        # T = [21, 10, 13, 13, 13, 1, 1]

        #...deprecated

        #define the over frequency shall-trip region
        OFtripPoints = [
            Point(fMaxTheo, self.__Settings['OF2 CT - sec']),
            Point(self.__Settings['OF2 - Hz'], self.__Settings['OF2 CT - sec']),
            Point(self.__Settings['OF2 - Hz'], self.__Settings['OF1 CT - sec']),
            Point(self.__Settings['OF1 - Hz'], self.__Settings['OF1 CT - sec']),
            Point(self.__Settings['OF1 - Hz'], tMax),
            Point(fMaxTheo, tMax)
        ]
        OFtripRegion = Polygon([[p.y, p.x] for p in OFtripPoints])

        #define the under frequency shall-trip region
        UFtripPoints = [
            Point(0, self.__Settings['UF2 CT - sec']),
            Point(self.__Settings['UF2 - Hz'], self.__Settings['UF2 CT - sec']),
            Point(self.__Settings['UF2 - Hz'], self.__Settings['UF1 CT - sec']),
            Point(self.__Settings['UF1 - Hz'], self.__Settings['UF1 CT - sec']),
            Point(self.__Settings['UF1 - Hz'], tMax),
            Point(0, tMax)
        ]
        UFtripRegion = Polygon([[p.y, p.x] for p in UFtripPoints])

        if self.__Settings['Ride-through Category'] in ['Category I', 'Category II', 'Category III']:

            #check over frequency points
            if self.__Settings['OF2 - Hz'] < 61.8 or self.__Settings['OF2 - Hz'] > 66:
                #print("User defined setting outside of IEEE 1547 acceptable range.")
                assert False

            if self.__Settings['OF2 CT - sec'] < 0.16 or self.__Settings['OF2 CT - sec'] > 1000:
                #print("User defined setting outside of IEEE 1547 acceptable range.")
                assert False

            if self.__Settings['OF1 - Hz'] < 61.0 or self.__Settings['OF1 - Hz'] > 66.0:
                #print("User defined setting outside of IEEE 1547 acceptable range.")
                assert False

            if self.__Settings['OF1 CT - sec'] <180 or self.__Settings['OF1 CT - sec'] > 1000:
                #print("User defined setting outside of IEEE 1547 acceptable range.")
                assert False
            #check under frequency points
            if self.__Settings['UF2 - Hz'] > 57.0 or self.__Settings['UF2 - Hz'] < 50:
                #print("User defined setting outside of IEEE 1547 acceptable range.")
                assert False

            if self.__Settings['UF2 CT - sec'] < 0.16 or self.__Settings['UF2 CT - sec'] > 1000:
                #print("User defined setting outside of IEEE 1547 acceptable range.")
                assert False

            if self.__Settings['UF1 - Hz'] < 50 or self.__Settings['UF1 - Hz'] > 59.0:
                #print("User defined setting outside of IEEE 1547 acceptable range.")
                assert False

            if self.__Settings['UF1 CT - sec'] < 180 or self.__Settings['UF1 CT - sec'] > 1000:
                #print("User defined setting outside of IEEE 1547 acceptable range.")
                assert False

      
            # F = [1.10, 0.88, 0.7, 1.20, 1.175, 1.15, 0.50, 0.5]
            # T = [1.5,   0.7, 0.2, 0.50, 1.000, 0.16, 0.16]
            self.__faultCounterMax = 2
            self.__faultCounterClearingTimeSec = 20

        else:
            assert False

        self._ControlledElm.SetParameter('Model', '7')
        # self._ControlledElm.SetParameter('Vmaxpu', V[0])
        # self._ControlledElm.SetParameter('Vminpu', V[1])


        ContinuousPoints = [Point(self.__continuous_f_upper, 0), Point(self.__continuous_f_upper, tMax), Point(self.__continuous_f_lower, tMax), Point(self.__continuous_f_lower, 0)]
        ContinuousRegion = Polygon([[p.y, p.x] for p in ContinuousPoints])

        MandatoryPoints1 = [Point(61.8, 0), Point(61.8, 299), Point(self.__continuous_f_upper, 299), Point(self.__continuous_f_upper, 0)]
        MandatoryRegion1 = Polygon([[p.y, p.x] for p in MandatoryPoints1])

        MandatoryPoints2 = [Point(self.__continuous_f_lower, 0), Point(self.__continuous_f_lower, 299), Point(57.0, 299), Point(57.0, 0)]
        MandatoryRegion2 = Polygon([[p.y, p.x] for p in MandatoryPoints2])

        # PermissiveOVPoints = [Point(V[3], 0), Point(V[3], T[2]), Point(V[4], T[2]), Point(V[4], T[3]),
        #                       Point(V[5], T[3]),
        #                       Point(V[5], T[4]), Point(V[0], T[4]), Point(V[0], 0.0)]
        # PermissiveOVRegion = Polygon([[p.y, p.x] for p in PermissiveOVPoints])

        # PermissiveUVPoints = [Point(V[2], 0), Point(V[2], T[5]), Point(V[6], T[5]), Point(V[6], T[6]),
        #                       Point(V[7], T[6]), Point(V[7], 0)]
        # PermissiveUVRegion = Polygon([[p.y, p.x] for p in PermissiveUVPoints])

        ActiveRegion = MultiPolygon([OFtripRegion, UFtripRegion, ContinuousRegion, 
                                    MandatoryRegion1,MandatoryRegion2])


        TotalPoints = [Point(fMaxTheo, 0), Point(fMaxTheo, tMax), Point(0, tMax), Point(0, 0)]
        TotalRegion = Polygon([[p.y, p.x] for p in TotalPoints])
        intersection = TotalRegion.intersection(ActiveRegion)
        MayTripRegion = TotalRegion.difference(intersection) #everything not in the active region is the white "may trip" 

        if self.__Settings['May trip operation'] == 'Trip':
            self.CurrLimRegion = cascaded_union([MandatoryRegion1, MandatoryRegion2]) #Naming probably not appropriate with frequency variation.  
            self.TripRegion = cascaded_union([OFtripRegion, UFtripRegion, MayTripRegion])
        elif self.__Settings['May trip operation'] == 'Ride-Through':
            self.CurrLimRegion = cascaded_union([MandatoryRegion1, MandatoryRegion2, MayTripRegion])
            self.TripRegion = cascaded_union([OFtripRegion, UFtripRegion])
        else:
            assert False
        self.ContinuousRegion = ContinuousRegion
      
        
        return 

    def calculate_frequency(self, priority, time):    
        vsrc = self._ElmObjectList["Vsource.source"]
        u_ang = vsrc.GetParameter("angle")
        u_ang = u_ang * math.pi / 180
        
        if priority == 2:
            if time <= 1:
                bus_freq = self.__dssSolver.getFrequency()
                self.u_ang = u_ang
            else:
                h = self.__dssSolver.GetStepSizeSec()
                tau = h * 4
                dphi = (u_ang - self.u_ang) / (2 * math.pi * h)
                self.df = (dphi + self.df * (tau / h) ) / ( 1 + tau / h )    
                base_freq = self.__dssSolver.getFrequency()
                bus_freq = base_freq + self.df 
                self.u_ang = u_ang

            self.freq_hist.append(bus_freq)
            return bus_freq


    def Update(self, Priority, Time, Update):
        Error = 0
        self.TimeChange = self.Time != (Priority, Time)
        self.Time = Time
        
        self.freq = self.calculate_frequency(Priority, Time)
       
        
        if Priority == 0:
            if self.Time == 0:
                self.u_ang = self._ControlledElm.GetVariable('VoltagesMagAng')[1::2][0]
            self.__isConnected = self.__Connect()
  
        if Priority == 2: 
            
            if self.Time == 719:
                fig, ax = plt.subplots()
                ax.plot(self.freq_hist[:-3])
                plt.show()
            
        #     fIn = self.__UpdateViolatonTimers()
        #     if self.__Settings["Follow standard"] == "1547-2018":
        #         self.FrequencyRideThrough(fIn)
        #     elif self.__Settings["Follow standard"] == "1547-2003":
        #         self.Trip(fIn)
        #     else:
        #         raise Exception("Valid standard setting defined. Options are: 1547-2003, 1547-2018")
            
        #     P = -sum(self._ControlledElm.GetVariable('Powers')[::2])
        #     self.power_hist.append(P)
        #     self.frequency_hist.append(fIn)
        #     self.timer_hist.append(self.__fViolationtime)
        #     self.timer_act_hist.append(self.__dssSolver.GetTotalSeconds())

        # if self.Time == 39 and Priority==2: # Time is the time step, 
        #     import matplotlib.pyplot as plt
        #     fig, (ax1, ax2) = plt.subplots(2,1)

        #     models = [self.CurrLimRegion, self.TripRegion, MultiPolygon([self.ContinuousRegion])]                    
        #     models = [i for i in models if i is not None]      
            
        #     colors = ["orange", "red", "green"]
        #     for m, c in zip(models, colors):
        #         for geom in m.geoms:    
        #             xs, ys = geom.exterior.xy    
        #             ax1.fill(xs, ys, alpha=0.35, fc=c, ec='none')


        #     ax1.set_xlim(0, 2)
        #     ax1.set_ylim(55, 65)
        #     # ax1.scatter( self.timer_hist, self.frequency_hist)
        #     ax1.scatter( self.timer_act_hist, self.frequency_hist)
        #     ax3 = ax2.twinx()
        #     ax2.set_ylabel('Power (kW) in green')
        #     ax3.set_ylabel('Frequency in red')
        #     ax2.plot(self.timer_act_hist[1:], self.power_hist[1:], c="green")
        #     ax3.plot(self.timer_act_hist[1:], self.frequency_hist[1:], c="red")
        #     fig.savefig(f"C:/Users/jkeen/Desktop/{self.__Name}_{self.__Settings['Ride-through Category']}_test.png")
  
        return Error

    def Trip(self, fIn):
        """ Implementation of the IEEE1587-2003 voltage ride-through requirements for inverter systems
        """
        if fIn < 59.3 or fIn > 60.5: # see page 19 of 1547-2003. #todo: more parameters are possible.  
            if self.__isConnected:
                self.__Trip(30.0, 0.4, False) #__Trip(self, Deadtime, Time2Pmax, forceTrip, permissive_to_trip=False)
        return

    def FrequencyRideThrough(self, fIn):
        """ Implementation of the IEEE1587-2018 voltage ride-through requirements for inverter systems
        """
        self.__faultCounterClearingTimeSec = 1
        Pm = Point(self.__fViolationtime, fIn)
        if Pm.within(self.CurrLimRegion):
            region = 0
            isinContinuousRegion = False

        elif Pm.within(self.TripRegion):
            region = 2
            isinContinuousRegion = False
            if self.region == [3, 1, 1]: #Why? What is this region logic?
                self.__Trip(self.__trip_deadtime_sec, self.__Time_to_Pmax_sec, False, True)
            else: 
                self.__Trip(self.__trip_deadtime_sec, self.__Time_to_Pmax_sec, False)
        else:
            isinContinuousRegion = True
            region = 3
            
        self.region = self.region[1:] + self.region[:1]
        self.region[0] = region

        #if we were not originally in a continous region and we transitioned to a continous region, reset the fault timer counter
        if isinContinuousRegion and not self.__isinContinuousRegion:
            self.__FaultwindowClearingStartTime = self.__dssSolver.GetDateTime()
        #Keep track of time under fault conditions.  
        clearingTime = (self.__dssSolver.GetDateTime() - self.__FaultwindowClearingStartTime).total_seconds() 

        #if we were in a continuous region and transition to fault region
        if self.__isinContinuousRegion and not isinContinuousRegion:
            if  clearingTime <= self.__faultCounterClearingTimeSec: # faultCounterClearingTimeSec is set to 1 in this function. Is this logic right??  
                self.__faultCounter += 1
                if self.__faultCounter > self.__faultCounterMax:
                    if self.__Settings['Multiple disturbances'] == 'Trip':
                        self.__Trip(self.__trip_deadtime_sec, self.__Time_to_Pmax_sec, True)
                        self.__faultCounter = 0
                    else:
                        pass
        if  clearingTime > self.__faultCounterClearingTimeSec and self.__faultCounter > 0:
            self.__faultCounter = 0
        self.__isinContinuousRegion = isinContinuousRegion
        return

    def __Connect(self):
        if not self.__isConnected:
            aIn = self._ControlledElm.GetVariable('VoltagesMagAng')[::2]
            fIn = self.f_temp  #62.5 #should be some function of aIn
            if self.useAvgFrequency:
                self.frequency = self.frequency[1:] + self.frequency[:1] #WHY??
                self.frequency[0] = fIn
                fIn = sum(self.frequency) / len(self.frequency)
            deadtime = (self.__dssSolver.GetDateTime() - self.__TrippedStartTime).total_seconds()
            if fIn < self.__continuous_f_upper and fIn > self.continuous_f_lower and deadtime >= self.__TrippedDeadtime:
                self._ControlledElm.SetParameter('enabled', True)
                self.__isConnected = True
                self._ControlledElm.SetParameter('kw', 0)
                self.__ReconnStartTime = self.__dssSolver.GetDateTime()
        else:
            conntime = (self.__dssSolver.GetDateTime() - self.__ReconnStartTime).total_seconds()
            self.__Plimit = conntime / self.__TrippedPmaxDelay * self.__Prated if conntime < self.__TrippedPmaxDelay \
                else self.__Prated
            self._ControlledElm.SetParameter('kw', self.__Plimit)
        return self.__isConnected

    def __Trip(self, Deadtime, Time2Pmax, forceTrip, permissive_to_trip=False):
        #Why? Is this logic right?  They look the same? Change to: "if self.__isConnected or forceTrip or permissive_to_trip"
        if self.__isConnected or forceTrip:

            self._ControlledElm.SetParameter('enabled', False)

            self.__isConnected = False
            self.__TrippedStartTime = self.__dssSolver.GetDateTime()
            self.__TrippedPmaxDelay = Time2Pmax
            self.__TrippedDeadtime = Deadtime
            
        elif permissive_to_trip:
    
            self._ControlledElm.SetParameter('enabled', False)

            self.__isConnected = False
            self.__TrippedStartTime = self.__dssSolver.GetDateTime()
            self.__TrippedPmaxDelay = Time2Pmax
            self.__TrippedDeadtime = Deadtime
        return

    
    def __UpdateViolatonTimers(self):
        aIn = self._ControlledElm.GetVariable('VoltagesMagAng')[::2]
        fIn = self.f_temp  #62.5 #should be some function of aIn

        if self.useAvgFrequency:
            self.frequency = self.frequency[1:] + self.frequency[:1] #WHY??  I think we're trying to insert new element at first position and remove last
            self.frequency[0] = fIn
            fIn = sum(self.frequency) / len(self.frequency)

        #track how long we've been operating under normal or abnormal conditions
        if fIn < self.__continuous_f_upper and fIn > self.__continuous_f_lower:
            if not self.__NormOper:
                self.__NormOper = True
                self.__NormOperStartTime = self.__dssSolver.GetDateTime()
                self.__NormOperTime = 0
            else:
                self.__NormOperTime = (self.__dssSolver.GetDateTime() - self.__NormOperStartTime).total_seconds()
            self.__FreqVioM = False
            # self.__VoltVioP = False

        else: #not in continuous region
            if not self.__FreqVioM:
                self.__FreqVioM = True
                self.__fViolationstartTime = self.__dssSolver.GetDateTime()
                self.__fViolationtime = 0
            else:
                self.__fViolationtime = (self.__dssSolver.GetDateTime() - self.__fViolationstartTime).total_seconds()


        return fIn
