"""Test registry."""

import copy
import os
from pathlib import Path

import pytest

from pydss.common import ControllerType
from pydss.registry import Registry, DEFAULT_REGISTRY


# Don't change the user's registry.
TEST_FILENAME = Path("tests") / "pydss_test_registry.json"
CTYPE = ControllerType.PV_CONTROLLER.value


@pytest.fixture
def registry_fixture():
    yield
    if os.path.exists(TEST_FILENAME):
        os.remove(TEST_FILENAME)


def test_registry__list_controllers(registry_fixture):
    registry = Registry(registry_filename=TEST_FILENAME)
    registry.reset_defaults()
    actual = registry.list_controllers(CTYPE)
    expected = DEFAULT_REGISTRY["Controllers"][CTYPE]
    assert len(actual) == len(expected)


def test_registry__register_controllers(registry_fixture):
    registry = Registry(registry_filename=TEST_FILENAME)
    registry.reset_defaults()
    new_controller = copy.deepcopy(DEFAULT_REGISTRY["Controllers"][CTYPE][0])
    new_name = new_controller["name"] + "_new"
    new_controller["name"] = new_name
    registry.register_controller(CTYPE, new_controller)

    # Test that the the changes are reflected with a new instance.
    registry2 = Registry(registry_filename=TEST_FILENAME)
    controllers1 = registry.list_controllers(CTYPE)
    controllers2 = registry2.list_controllers(CTYPE)
    for data1, data2 in zip(controllers1, controllers2):
        for field in DEFAULT_REGISTRY["Controllers"][CTYPE][0]:
            assert data1[field] == data2[field]

    registry2.unregister_controller(CTYPE, new_name)
    assert not registry2.is_controller_registered(CTYPE, new_name)


def test_registry__is_controller_registered(registry_fixture):
    registry = Registry(registry_filename=TEST_FILENAME)
    registry.reset_defaults()
    assert registry.is_controller_registered(
        CTYPE, DEFAULT_REGISTRY["Controllers"][CTYPE][0]["name"]
    )


def test_registry__reset_defaults(registry_fixture):
    registry = Registry(registry_filename=TEST_FILENAME)
    registry.reset_defaults()
    assert len(registry.list_controllers(CTYPE)) == len(DEFAULT_REGISTRY["Controllers"][CTYPE])


def test_registry__show_controllers(capsys, registry_fixture):
    """Test functionality of show_controllers."""
    registry = Registry(registry_filename=TEST_FILENAME)
    registry.reset_defaults()
    registry.show_controllers()
    captured = capsys.readouterr()
    for controller in DEFAULT_REGISTRY["Controllers"][CTYPE]:
        assert controller["name"] in captured.out
