from pydantic import ConfigDict, BaseModel, model_validator
from typing import List, Optional, Any, Union, Dict
from enum import Enum
import helics
import os
import re
import pandas as pd
from loguru import logger

from pydss.simulation_input_models import SimulationSettingsModel
from pydss.common import SUBSCRIPTIONS_FILENAME, ExportMode
from pydss.utils.utils import load_data

TYPE_INFO = {
        'CurrentsMagAng': 'vector',
        'Currents': 'vector',
        'RatedCurrent': 'double',
        'EmergAmps': 'double',
        'NormalAmps': 'double',
        'normamps': 'double',
        'Losses': 'vector',
        'PhaseLosses': 'vector',
        'Powers': 'vector',
        'TotalPower': 'vector',
        'LineLosses': 'vector',
        'SubstationLosses': 'vector',
        'kV': 'double',
        'kVARated': 'double',
        'kvar': 'double',
        'kW': 'double',
        'kVABase': 'double',
        'kWh': 'double',
        'puVmagAngle': 'vector',
        'VoltagesMagAng': 'vector',
        'VMagAngle': 'vector',
        'Voltages': 'vector',
        'Vmaxpu': 'double',
        'Vminpu': 'double',
        'Frequency': 'double',
        'Taps': 'vector',
        '%stored': 'double',
        'Distance': 'double'
    }

class DataType(Enum):
    DOUBLE = "double"
    VECTOR = "vector"
    STRING = "string"
    BOOLEAN = "boolean"
    INTEGER = "integer"

class Subscription(BaseModel):
    model: str
    property: str
    id: str
    unit: Optional[str] = None 
    subscribe: bool = True
    data_type: DataType
    multiplier: float = 1.0
    object: Any = None
    states: List[Union[float, int, bool]] = [0.0, 0.0, 0.0, 0.0, 0.0]
    sub: Any = None
    model_config = ConfigDict(arbitrary_types_allowed=True)
    multi_input_ids: List[str] = None
    multi_input_handling_method: str = 'no_op'

class Publication(BaseModel):
    model: str
    property: str
    id: str
    object: Any = None
    pub: Any = None
    data_type: DataType
    
class Subscriptions(BaseModel):
    federate: Any = None
    opendss_models: Dict
    subscriptions: List[Subscription]

    @model_validator(mode='after')
    def is_in_opendss_model(self)-> 'Subscriptions':        
        for subscription in self.subscriptions:
            if subscription.model not in self.opendss_models:
                raise AssertionError(f"The loaded OpenDSS model does not have an element define with the name {subscription}")
            if subscription.subscribe:
                subscription.object = self.opendss_models[subscription.model]
                if subscription.multi_input_ids:
                    subscription.sub = helics.helicsFederateRegisterInput(self.federate, helics.helics_data_type_double, "")
                    for input_id in subscription.multi_input_ids:
                        helics.helicsInputAddTarget(subscription.sub, input_id)
                    helics.helicsInputSetOption(subscription.sub, helics.helics_handle_option_multi_input_handling_method,
                        subscription.multi_input_handling_method)
                else:
                    subscription.sub = helics.helicsFederateRegisterSubscription(
                        self.federate,
                        subscription.id,
                        subscription.unit
                    )
        return self
    
class Publications(BaseModel):
    
    federate: Any = None
    federate_name: str
    opendss_models: Dict
    publications: List[Publication] = []
    legacy_input: Dict = {}
    input: Dict = {}
    
    @model_validator(mode='after')
    def build_from_legacy(self)-> 'Publications':
        publications = []
        for object_type, k in self.legacy_input.items():
            if object_type in self.opendss_models:
                models =  self.opendss_models[object_type]    
                for model in models:
                    for ppty in k['Publish']:
                        name = '{}.{}.{}'.format(self.federate_name, model, ppty)
                        pub_dict = {
                            "model" : model,
                            "object" :  models[model],
                            "id" : name,
                            "property" : ppty,
                            "data_type" : TYPE_INFO[ppty],
                            "pub" :  helics.helicsFederateRegisterGlobalTypePublication(
                                self.federate,
                                name,
                                TYPE_INFO[ppty],
                                ''
                            )
                        }
                        publications.append(Publication.model_validate(pub_dict))
        self.publications = publications
        return self

    @model_validator(mode='after')
    def build_from_export(self)-> 'Publications':
        publications = []
        for object_type, export_properties in self.input.items():
            if object_type in self.opendss_models:
                models =  self.opendss_models[object_type]
                for export_property in export_properties:
                    filtered_models = {}
                    if export_property['publish']:
                        if 'names' in export_property and export_property['names']:
                            for k, v in models.items():
                                if k in export_property['names']:
                                    filtered_models[k] = models[k]
                        elif 'name_regexes' in export_property and export_property['name_regexes']:
                            for regex_expression in export_property['name_regexes']:
                                r = re.compile(regex_expression)
                                matches = list(filter(r.match, models.keys()))
                                for match in matches:
                                    filtered_models[match] = models[match]
                        else:
                            filtered_models = models
                    
                        for model_name, model_obj in filtered_models.items():
                            if object_type == "Buses":
                                name = '{}.Bus.{}.{}'.format(self.federate_name, model_name, export_property["property"])
                            else:
                                name = '{}.{}.{}'.format(self.federate_name, model_name, export_property["property"])
                            pub_dict = {
                                "model" : model_name,
                                "object" :  model_obj,
                                "id" : name,
                                "property" : export_property["property"],
                                "data_type" : TYPE_INFO[export_property["property"]],
                                "pub" :  helics.helicsFederateRegisterGlobalTypePublication(
                                    self.federate,
                                    name,
                                    TYPE_INFO[export_property["property"]],
                                    ''
                                )
                            }
                            publications.append(Publication.model_validate(pub_dict))
        self.publications = publications        
        return self

class helics_interface:
    n_states = 5
    init_state = 1
    
    def __init__(self, dss_solver, objects_by_name, objects_by_class, settings: SimulationSettingsModel, system_paths, default=True):
        self.itr = 0
        self.c_seconds = 0
        self.c_seconds_old = -1
        self._settings = settings
        self._co_convergance_error_tolerance = settings.helics.error_tolerance
        self._co_convergance_max_iterations = self._settings.helics.max_co_iterations
        self._publications = {}
        self._system_paths = system_paths
        self._objects_by_element = objects_by_name
        self._objects_by_class = objects_by_class
        self._create_helics_federate()
        self._dss_solver = dss_solver
        if default:
            self.registerPubSubTags()

    def registerPubSubTags(self, pubs=None, subs=None):

        self._registerFederateSubscriptions(subs)
        self._registerFederatePublications(pubs)

        helics.helicsFederateEnterExecutingModeIterative(
            self._federate,
            helics.helics_iteration_request_iterate_if_needed
        )
        logger.info('Entered HELICS execution mode')

    def _create_helics_federate(self):
        self.fedinfo = helics.helicsCreateFederateInfo()
        helics.helicsFederateInfoSetCoreName(self.fedinfo, self._settings.helics.federate_name)
        helics.helicsFederateInfoSetCoreTypeFromString(self.fedinfo, self._settings.helics.core_type)
        helics.helicsFederateInfoSetCoreInitString(self.fedinfo, f"--federates=1")
        IP = self._settings.helics.broker
        Port = self._settings.helics.broker_port
        logger.info("Connecting to broker @ {}".format(f"{IP}:{Port}" if Port else IP))
        logger.info(f"Connecting to broker @ {self._settings.helics}")
        if self._settings.helics.broker:
            helics.helicsFederateInfoSetBroker(self.fedinfo, str(self._settings.helics.broker))
        if self._settings.helics.broker_port:
            helics.helicsFederateInfoSetBrokerPort(self.fedinfo, self._settings.helics.broker_port)
        helics.helicsFederateInfoSetTimeProperty(self.fedinfo, helics.helics_property_time_delta,
                                                 self._settings.helics.time_delta)
        helics.helicsFederateInfoSetIntegerProperty(self.fedinfo, helics.helics_property_int_log_level,
                                                    self._settings.helics.logging_level)
        helics.helicsFederateInfoSetIntegerProperty(self.fedinfo, helics.helics_property_int_max_iterations,
                                                    self._settings.helics.max_co_iterations)
        self._federate = helics.helicsCreateValueFederate(self._settings.helics.federate_name, self.fedinfo)
        return


    def _registerFederateSubscriptions(self, subscriptions:Subscriptions = None):
        """
        :param subs:
        :return:
        """
        if subscriptions is None:
            subscription_file = os.path.join(
                self._system_paths["ExportLists"],
                SUBSCRIPTIONS_FILENAME,
            )
            assert os.path.exists(subscription_file), f"The following file does not exist: {subscription_file}"
            file_data = load_data(subscription_file)
            file_data["opendss_models"] = self._objects_by_element
            file_data["federate"] = self._federate
         
            self.subscriptions = Subscriptions.model_validate(file_data)
        else:
            self.subscriptions = subscriptions
        logger.info(str(self.subscriptions.subscriptions))
        for subscription in self.subscriptions.subscriptions:
            logger.info(f"subscription created: {subscription}")
        return

    def updateHelicsSubscriptions(self):
        for subscription in self.subscriptions.subscriptions:
            if subscription.subscribe:
                value = None
                if subscription.data_type == DataType.DOUBLE:
                    value = helics.helicsInputGetDouble(subscription.sub)
                elif subscription.data_type == DataType.VECTOR:
                    value = helics.helicsInputGetVector(subscription.sub)
                elif subscription.data_type == DataType.STRING:
                    value = helics.helicsInputGetString(subscription.sub)
                elif subscription.data_type == DataType.BOOLEAN:
                    value = helics.helicsInputGetBoolean(subscription.sub)
                elif subscription.data_type == DataType.INTEGER:
                    value = helics.helicsInputGetInteger(subscription.sub)
                    
                if value and value != 0:
                    logger.info(f"value is {value}")
                    if value > 1e6 or value < -1e6 or pd.isna(value):
                        value = 1.0

                value = value * subscription.multiplier
                subscription.object.SetParameter(subscription.property, value) 
                logger.info('Value for "{}.{}" changed to "{}"'.format(
                        subscription.model,
                        subscription.property,
                        value
                    ))

                if self._settings.helics.iterative_mode:
                    if self.c_seconds != self.c_seconds_old:
                        subscription.states = [self.init_state] * self.n_states
                    else:
                        subscription.states.insert(0, subscription.states.pop())
                    subscription.states[0] = value

        self.c_seconds_old = self.c_seconds
  
    def _registerFederatePublications(self, publications:Publications = None):
        if publications:
            self.publicatiuons = publications
        else:
            legacy_export_file = os.path.join(
                self._system_paths ["ExportLists"],
                ExportMode.BY_CLASS.value + ".toml",
            )
            export_file = os.path.join(
                self._system_paths ["ExportLists"],
                ExportMode.EXPORTS.value  + ".toml",
            )
            
            publication_dict = {
                "opendss_models" : self._objects_by_class,
                "federate_name" : self._settings.helics.federate_name,
                "federate" : self._federate,
            }
                  
            if os.path.exists(export_file):
                export_data = load_data(export_file)
                publication_dict["input"] = export_data     
            elif os.path.exists(legacy_export_file):
                legacy_data = load_data(legacy_export_file)
                publication_dict["legacy_input"] = legacy_data               
            else:
                raise FileNotFoundError("No valid export settings found for the current scenario")
            
            self.publications = Publications.model_validate(publication_dict)
            logger.info(str(self.publications.publications))
            for publication in self.publications.publications:
                logger.info(f"pubscription created: {publication}")
        return

    def updateHelicsPublications(self):
        
        for publication in self.publications.publications:
            value = publication.object.GetValue(publication.property)
            
            if publication.data_type == DataType.VECTOR:
                helics.helicsPublicationPublishVector(publication.pub, value)
            elif publication.data_type == DataType.DOUBLE:
                helics.helicsPublicationPublishDouble(publication.pub, value)
            elif publication.data_type == DataType.STRING:
                helics.helicsPublicationPublishString(publication.pub, value)
            elif publication.data_type == DataType.BOOLEAN:
                helics.helicsPublicationPublishBoolean(publication.pub, value)
            elif publication.data_type == DataType.INTEGER:
                helics.helicsPublicationPublishInteger(publication.pub, value)
            else:
                raise ValueError("Unsupported data type forr teh HELICS interface")
            logger.info(f"{publication} - {value}")
        return

    def request_time_increment(self):
        error = sum([abs(sub.states[0] - sub.states[1]) for sub in self.subscriptions.subscriptions])
        # r_seconds = self._dss_solver.GetTotalSeconds() # parallel
        r_seconds = self._dss_solver.GetTotalSeconds() + self._dss_solver.GetStepResolutionSeconds() # transmission priority
        # if r_seconds > 0:
        #     r_seconds = self._dss_solver.GetTotalSeconds() + self._dss_solver.GetStepResolutionSeconds()
        # logger.info(f"self._dss_solver.GetTotalSeconds(): {self._dss_solver.GetTotalSeconds()}, self._dss_solver.GetStepResolutionSeconds(): {self._dss_solver.GetStepResolutionSeconds()}")
        # os.system('PAUSE')
        if not self._settings.helics.iterative_mode:
            while self.c_seconds < r_seconds:
                self.c_seconds = helics.helicsFederateRequestTime(self._federate, r_seconds)
            logger.info('Time requested: {} - time granted: {} '.format(r_seconds, self.c_seconds))
            return True, self.c_seconds
        else:

            self.c_seconds, iteration_state = helics.helicsFederateRequestTimeIterative(
                self._federate,
                r_seconds,
                helics.helics_iteration_request_iterate_if_needed
            )

            logger.info('Time requested: {} - time granted: {} error: {} it: {}'.format(
                r_seconds, self.c_seconds, error, self.itr))
            if error > -1 and self.itr < self._co_convergance_max_iterations - 1:
                self.itr += 1
                return False, self.c_seconds
            else:
                self.itr = 0
                return True, self.c_seconds
    
    def request_time_increment_2(self):
        error = sum([abs(sub.states[0] - sub.states[1]) for sub in self.subscriptions.subscriptions])
        r_seconds = self._dss_solver.GetTotalSeconds() + self._dss_solver.GetStepResolutionSeconds()/2
        # logger.info('Time requested: {} - self._dss_solver.GetStepResolutionSeconds(): {} '.format(r_seconds, self._dss_solver.GetStepResolutionSeconds()))
        # os.system('PAUSE')
        if not self._settings.helics.iterative_mode:
            while self.c_seconds < r_seconds:
                self.c_seconds = helics.helicsFederateRequestTime(self._federate, r_seconds)
            logger.info('Time requested: {} - time granted: {} '.format(r_seconds, self.c_seconds))
            return True, self.c_seconds
        else:

            self.c_seconds, iteration_state = helics.helicsFederateRequestTimeIterative(
                self._federate,
                r_seconds,
                helics.helics_iteration_request_iterate_if_needed
            )

            logger.info('Time requested: {} - time granted: {} error: {} it: {}'.format(
                r_seconds, self.c_seconds, error, self.itr))
            if error > -1 and self.itr < self._co_convergance_max_iterations - 1:
                self.itr += 1
                return False, self.c_seconds
            else:
                self.itr = 0
                return True, self.c_seconds

    def __del__(self):
        helics.helicsFederateDisconnect(self._federate)
        state = helics.helicsFederateGetState(self._federate)
        helics.helicsFederateInfoFree(self.fedinfo)
        helics.helicsFederateFree(self._federate)
        logger.info('HELICS federate for pydss destroyed')
