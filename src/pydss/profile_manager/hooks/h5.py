from pydss.profile_manager.base_definitions import BaseProfileManager, BaseProfile
from pydss.profile_manager.common import ProfileType
from pydss.exceptions import InvalidParameter
from pydss.common import DATE_FORMAT
import pandas as pd
import numpy as np
import datetime
import h5py
import copy
import os


class ProfileManager(BaseProfileManager):
    def __init__(self, sim_instance, solver, options, logger, **kwargs):
        super(ProfileManager, self).__init__(sim_instance, solver, options, logger, **kwargs)
        self.Objects = kwargs["objects"]
        if os.path.exists(self.basepath):
            self.logger.info("Loading existing h5 store")
            self.store = h5py.File(self.basepath, "r+")
        else:
            self.logger.info("Creating new h5 store")
            self.store = h5py.File(self.basepath, "w")
            for profile_group in ProfileType.names():
                self.store.create_group(profile_group)
        self.setup_profiles()
        return

    def setup_profiles(self):
        self.Profiles = {}
        for group, profile_map in self.mapping.items():
            if group in self.store:
                grp = self.store[group]
                for profile_name, mapping_dict in profile_map.items():
                    if profile_name in grp:
                        objects = {x["object"]: self.Objects[x["object"]] for x in mapping_dict}
                        self.Profiles[f"{group}/{profile_name}"] = Profile(
                            self.sim_instance,
                            grp[profile_name],
                            objects,
                            self.solver,
                            mapping_dict,
                            self.logger,
                            **self.kwargs,
                        )
                    else:
                        self.logger.warning(
                            "Group {} / data set {} not found in the h5 store".format(
                                group, profile_name
                            )
                        )
            else:
                self.logger.warning("Group {} not found in the h5 store".format(group))
        return

    def create_dataset(self, dname, profile_type, data, start_time, resolution, units, info):
        grp = self.store[profile_type]
        if dname not in grp:
            dset = grp.create_dataset(
                dname,
                data=data,
                shape=(len(data),),
                maxshape=(None,),
                chunks=True,
                compression="gzip",
                compression_opts=4,
                shuffle=True,
            )
            self.create_metadata(dset, start_time, resolution, data, units, info)
        else:
            self.logger.error(
                'Dataset "{}" already exists in group "{}".'.format(dname, profile_type)
            )
            raise Exception(
                'Dataset "{}" already exists in group "{}".'.format(dname, profile_type)
            )

    def add_from_arrays(self, data, name, profile_type, start_time, resolution, units="", info=""):
        r, c = data.shape
        if r > c:
            for i in range(c):
                d = data[:, i]
                dname = name if i == 0 else "{}_{}".format(name, i)
                self.create_dataset(
                    dname=dname,
                    profile_type=profile_type,
                    data=d,
                    start_time=start_time,
                    resolution=resolution,
                    units=units,
                    info=info,
                )
        else:
            for i in range(r):
                d = data[i, :]
                dname = name if i == 0 else "{}_{}".format(name, i)
                self.create_dataset(
                    dname=dname,
                    profile_type=profile_type,
                    data=d,
                    start_time=start_time,
                    resolution=resolution,
                    units=units,
                    info=info,
                )
        return

    def add_profiles_from_csv(
        self, csv_file, name, profile_type, start_time, resolution_sec=900, units="", info=""
    ):
        data = pd.read_csv(csv_file).values
        self.add_profiles(
            data,
            name,
            profile_type,
            start_time,
            resolution_sec=resolution_sec,
            units=units,
            info=info,
        )

    def add_profiles(
        self, data, name, profile_type, start_time, resolution_sec=900, units="", info=""
    ):
        if type(start_time) is not datetime.datetime:
            raise InvalidParameter("startTime should be a python datetime object")
        if profile_type not in ProfileType.names():
            raise InvalidParameter(
                "Valid values for profile_type are {}".format(ProfileType.names())
            )
        if data:
            self.add_from_arrays(
                data, name, profile_type, start_time, resolution_sec, units=units, info=info
            )
        self.store.flush()
        return

    def create_metadata(self, dataset, start_time, resolution, data, units, info):
        metadata = {
            "sTime": str(start_time),
            "eTime": str(start_time + datetime.timedelta(seconds=resolution * len(data))),
            "resTime": resolution,
            "npts": len(data),
            "min": min(data),
            "max": max(data),
            "mean": np.mean(data),
            "units": units,
            "info": info,
        }
        for key, value in metadata.items():
            if isinstance(value, str):
                value = np.string_(value)
            dataset.attrs[key] = value
        return

    def remove_profile(self, profile_type, profile_name):
        return

    def update(self):
        results = {}
        for profile_name, profile in self.Profiles.items():
            result = profile.update()
            results[profile_name] = result
        return results


class Profile(BaseProfile):
    DEFAULT_SETTINGS = {"multiplier": 1, "normalize": False, "interpolate": False}

    def __init__(self, sim_instance, dataset, devices, solver, mapping_dict, logger, **kwargs):
        super(Profile, self).__init__(
            sim_instance, dataset, devices, solver, mapping_dict, logger, **kwargs
        )
        self.valueSettings = {x["object"]: {**self.DEFAULT_SETTINGS, **x} for x in mapping_dict}

        self.bufferSize = kwargs["bufferSize"]
        self.buffer = np.zeros(self.bufferSize)
        self.profile = dataset
        self.neglectYear = kwargs["neglectYear"]
        self.Objects = devices

        self.attrs = self.profile.attrs
        self.sTime = datetime.datetime.strptime(self.attrs["sTime"].decode(), DATE_FORMAT)
        self.eTime = datetime.datetime.strptime(
            self.attrs["eTime"].decode(), "%Y-%m-%d %H:%M:%S.%f"
        )
        self.simRes = solver.GetStepSizeSec()
        self.Time = copy.deepcopy(solver.GetDateTime())
        return

    def update_profile_settings(self):
        return

    def update(self, update_object_properties=True):
        self.Time = copy.deepcopy(self.solver.GetDateTime())
        if self.Time < self.sTime or self.Time > self.eTime:
            value = 0
            value1 = 0
        else:
            delta_time = (self.Time - self.sTime).total_seconds()
            n = int(delta_time / self.attrs["resTime"])
            value = self.profile[n]
            interpolation_time = (
                self.Time
                - (self.sTime + datetime.timedelta(seconds=int(n * self.attrs["resTime"])))
            ).total_seconds()
            value1 = (
                self.profile[n]
                + (self.profile[n + 1] - self.profile[n])
                * interpolation_time
                / self.attrs["resTime"]
            )
        if update_object_properties:
            for object_name, obj in self.Objects.items():
                if self.valueSettings[object_name]["interpolate"]:
                    value = value1
                mult = self.valueSettings[object_name]["multiplier"]
                if self.valueSettings[object_name]["normalize"]:
                    value_f = value / self.attrs["max"] * mult
                else:
                    value_f = value * mult
                obj.SetParameter(self.attrs["units"].decode(), value_f)
        return value


ProfileManager.createMetadata = ProfileManager.create_metadata
