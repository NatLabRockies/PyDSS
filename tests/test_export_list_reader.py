import pytest

from pydss.common import LimitsFilter, StoreValuesType
from pydss.exceptions import InvalidConfiguration, InvalidParameter
from pydss.export_list_reader import ExportListProperty, ExportListReader


EXPORT_LIST_FILE = "tests/data/exports/config.toml"
LEGACY_FILE = "tests/data/project/Scenarios/scenario1/ExportLists/ExportMode-byClass.toml"


def test_export_list_reader():
    reader = ExportListReader(EXPORT_LIST_FILE)
    assert reader.list_element_classes() == [
        "Buses",
        "Circuits",
        "Lines",
        "Loads",
        "PVSystems",
        "Transformers",
    ]
    assert reader.list_element_property_names("Buses") == ["Distance", "puVmagAngle"]
    prop = reader.get_element_properties("Buses", "puVmagAngle")[0]
    assert prop.store_values_type == StoreValuesType.ALL
    assert prop.should_store_name("bus2")
    assert prop.should_store_value(4.0)

    with pytest.raises(InvalidParameter):
        prop = reader.get_element_properties("invalid", "Losses")
    assert not reader.get_element_properties("Circuits", "invalid")


def test_export_list_reader__names():
    data = {"names": ["bus1", "bus2"], "property": "puVmagAngle"}
    export_prop = ExportListProperty("Buses", data)
    assert export_prop.should_store_name("bus1")
    assert export_prop.should_store_name("bus2")
    assert not export_prop.should_store_name("bus3")

    with pytest.raises(InvalidConfiguration):
        ExportListProperty("Buses", {"names": "bus1", "property": "puVmagAngle"})


def test_export_list_reader__name_regexes():
    data = {"property": "puVmagAngle", "name_regexes": [r"busFoo\d+", r"busBar\d+"]}
    export_prop = ExportListProperty("Buses", data)
    assert not export_prop.should_store_name("bus1")
    assert export_prop.should_store_name("busFoo23")
    assert export_prop.should_store_name("busBar8")


def test_export_list_reader__name_and_name_regexes():
    data = {"property": "puVmagAngle", "names": ["bus1"], "name_regexes": [r"busFoo\d+"]}
    with pytest.raises(InvalidConfiguration):
        ExportListProperty("Buses", data)


def test_export_list_reader__limits():
    data = {"property": "puVmagAngle", "limits": [-1.0, 1.0], "limits_filter": LimitsFilter.OUTSIDE}
    export_prop = ExportListProperty("Buses", data)
    assert export_prop.limits.min == -1.0
    assert export_prop.limits.max == 1.0
    assert export_prop.should_store_value(-2.0)
    assert export_prop.should_store_value(2.0)
    assert not export_prop.should_store_value(-0.5)
    assert not export_prop.should_store_value(0.5)

    data = {"property": "puVmagAngle", "limits": [-1.0, 1.0], "limits_filter": LimitsFilter.INSIDE}
    export_prop = ExportListProperty("Buses", data)
    assert export_prop.limits.min == -1.0
    assert export_prop.limits.max == 1.0
    assert not export_prop.should_store_value(-2.0)
    assert not export_prop.should_store_value(2.0)
    assert export_prop.should_store_value(
        -0.5,
    )
    assert export_prop.should_store_value(0.5)

    with pytest.raises(InvalidConfiguration):
        ExportListProperty("Buses", {"property": "puVmagAngle", "limits": [1.0]})

    with pytest.raises(InvalidConfiguration):
        ExportListProperty("Buses", {"property": "puVmagAngle", "limits": 1.0})


def test_export_list_reader__legacy_file():
    reader = ExportListReader(LEGACY_FILE)
    assert reader.list_element_classes() == [
        "Buses",
        "Circuits",
        "Lines",
        "Loads",
        "Storages",
        "Transformers",
    ]
    assert reader.list_element_property_names("Buses") == ["Distance", "puVmagAngle"]
    prop = reader.get_element_properties("Buses", "puVmagAngle")[0]
    assert prop.store_values_type == StoreValuesType.ALL
    assert prop.should_store_name("bus2")
    assert prop.should_store_value(4.0)
    assert reader.publicationList == [
        "Loads Powers",
        "Storages Powers",
        "Circuits TotalPower",
        "Circuits LineLosses",
        "Circuits Losses",
        "Circuits SubstationLosses",
    ]


def test_export_list_reader__window_size():
    prop = ExportListProperty(
        "Buses",
        {"property": "puVmagAngle", "store_values_type": "moving_average"},
    )
    assert prop.window_size == 100

    prop = ExportListProperty(
        "Buses",
        {
            "property": "puVmagAngle",
            "store_values_type": "moving_average",
            "window_size": 75,
        },
    )
    assert prop.window_size == 75
