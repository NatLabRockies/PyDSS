from enum import IntEnum


class ProfileType(IntEnum):
    Load = 0
    Generation = 1
    Irradiance = 2
    Temperature = 3
    Voltage = 4
    Current = 5
    EM_Price = 6
    AS_Price = 7
    WindProfile = 8

    @staticmethod
    def names():
        return list(map(lambda c: c.name, ProfileType))

    @staticmethod
    def values():
        return list(map(lambda c: c.value, ProfileType))


PROFILE_TYPES = ProfileType
