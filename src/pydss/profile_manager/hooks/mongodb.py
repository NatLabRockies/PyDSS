from pydss.profile_manager.base_definitions import BaseProfileManager, BaseProfile
from bson.objectid import ObjectId
from pymongo import MongoClient


class ProfileManager(BaseProfileManager):
    def __init__(self, sim_instance, solver, options, logger, **kwargs):
        super(ProfileManager, self).__init__(sim_instance, solver, options, logger, **kwargs)
        self.Objects = kwargs["objects"]
        usersettings = options["Profiles"]["settings"]

        # self.client = MongoClient(self.basepath, username=usersettings["username"], password=usersettings["password"])
        self.client = MongoClient(
            "mongodb://user:password@bmather-131003:27017/?authSource=admin&readPreference=primary&appname=MongoDB%20Compass&ssl=false&connect=false"
        )
        self.db_name = usersettings["database"]
        self.db = self.client[usersettings["database"]]
        self.collections = self.db.collection_names()
        self.mapping = usersettings["mapping"]
        # self.one_Time_fix(usersettings['collection'])
        self.setup_profiles()
        pass

    def one_time_fix(self, collection_name):
        self.logger.info("Creating aggregated load profiles")
        collection = self.db[collection_name]
        cursor = collection.find({"name": "customer_metadata"})
        customer_metadata = cursor.next()
        i = 0
        total_xfmr_load = {}
        for customer_id, customer_info in customer_metadata.items():
            if isinstance(customer_info, dict):
                agg_load = customer_info["section_id"]
                if agg_load not in total_xfmr_load:
                    total_xfmr_load[agg_load] = []
                total_xfmr_load[agg_load].append(customer_id)

            record = collection.find({"date": {"$exists": 1}})
        count = record.count()
        posts = []
        self.logger.info(f"Count: {count}")
        for i in range(count):
            total_load = {}
            profile_data = record.next()
            time = profile_data["date"]
            total_load["_id"] = ObjectId()
            total_load["date"] = time
            total_load["aggregated"] = True
            vars = ["kw", "kvar"]
            for var in vars:
                if var not in total_load:
                    total_load[var] = {}
                for load_name, loadlist in total_xfmr_load.items():
                    if load_name not in total_load[var]:
                        total_load[var][load_name] = 0
                    for elm, val in profile_data[var].items():
                        if elm in loadlist:
                            total_load[var][load_name] += val
            posts.append(total_load)
            collection.insert(total_load)
            self.logger.info(f"Percentage complete: {(i + 1) / count * 100.0}")
        self.logger.debug("Insert successful")

    def setup_profiles(self):
        for element_name, collection_name in self.mapping.items():
            if collection_name not in self.collections:
                raise Exception(
                    f"{collection_name} is not a valid collection for database {self.db_name}"
                )
            self.logger.info(f"Reading collection: {collection_name}")
            # for collection in self.collections:
            collection = self.db[collection_name]
            record = collection.find({"date": {"$exists": 1}})
            profile_data = record.next()
            profile_data.pop("_id", None)
            profile_data.pop("date", None)

            for property, obj_info in profile_data.items():
                if isinstance(obj_info, dict):
                    profile_dict = {}
                    for profile_name in obj_info:
                        if profile_name not in profile_dict:
                            profile_dict[profile_name] = []
                        model_found = False
                        for model_name, model in self.Objects.items():
                            if element_name in model_name and profile_name in model_name:
                                profile_dict[profile_name].append(model_name)
                                model_found = True
                                break
                        if not model_found:
                            self.logger.warning(
                                f"Profile {profile_name} could not be mapped to any element of type {collection_name} in the OpenDSS model"
                            )
                    for profile_name, model_list in profile_dict.items():
                        self.Profiles[f"{element_name}.{profile_name}.{property}"] = Profile(
                            self.sim_instance,
                            (collection_name, element_name, profile_name, property),
                            [self.Objects[x] for x in model_list],
                            self.solver,
                            None,
                            self.logger,
                            **self.kwargs,
                        )

    def update(self):
        self.logger.debug(self.solver.GetDateTime())
        for element_name, collection_name in self.mapping.items():
            collection = self.db[collection_name]
            record = collection.find({"date": self.solver.GetDateTime()})
            if not record.count():
                self.logger.warning(
                    f"No record found for time period {self.solver.GetDateTime()} in the database"
                )
            else:
                profile_data = record.next()
                profile_data.pop("_id", None)
                profile_data.pop("date", None)
                for profile in self.Profiles:
                    self.Profiles[profile].update(profile_data)
        pass


class Profile(BaseProfile):
    DEFAULT_SETTINGS = {"multiplier": 1, "normalize": False, "interpolate": False}

    def __init__(self, sim_instance, dataset, devices, solver, mapping_dict, logger, **kwargs):
        super(Profile, self).__init__(
            sim_instance, dataset, devices, solver, mapping_dict, logger, **kwargs
        )
        self.collection_name, self.class_name, self.profile_name, self.property = self.dataset

    def update_profile_settings(self):
        pass

    def update(self, update_object_properties=True):
        data = update_object_properties
        value = data[self.property][self.profile_name]
        for device in self.devices:
            device.SetParameter(self.property, value)


ProfileManager.one_Time_fix = ProfileManager.one_time_fix
