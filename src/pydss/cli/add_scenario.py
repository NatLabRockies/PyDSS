from pathlib import Path
import typer

from pydss.simulation_input_models import MappedControllers
from pydss.pydss_project import PyDssScenario
from pydss.common import CONTROLLER_TYPES, ControllerType
from pydss.utils import toml_utils


def build_scenario(project_path: str, scenario_name: str, controller_mapping: str):
    project_path = Path(project_path)
    controller_mapping_path = Path(controller_mapping)
    assert project_path.exists(), "Provided project path does not exist"
    assert (project_path / "Scenarios").exists(), "provided project is not a valid pydss project"
    assert controller_mapping_path.exists(), "rovided controller_mapping file does not exist"
    assert controller_mapping_path.suffix.lower() == ".toml", (
        "controller_mapping should be a TOML file"
    )

    controller_map = toml_utils.load(controller_mapping_path)
    mapped_controllers = MappedControllers(**controller_map)
    acceptable_controller_types = CONTROLLER_TYPES
    controllers = {}
    for controller in mapped_controllers.mapping:
        settings_path_obj = Path(controller.controller_file)
        assert controller.controller_type in ControllerType, (
            f"{controller.controller_type} is not a valid contoller. Options are {acceptable_controller_types}"
        )
        assert settings_path_obj.exists(), (
            f"file for controller type {controller.controller_type} does not exist"
        )
        controller_data = toml_utils.load(settings_path_obj)
        if controller_data:
            if controller.controller_type in controllers:
                msg = (
                    f"Multiple keys files for the same controller type {controller.controller_type}."
                    "Each controller type can only be attached to a single file."
                )
                raise ValueError(msg)
            controllers[controller.controller_type] = toml_utils.load(settings_path_obj)
    scenario_dir = project_path / "Scenarios" / scenario_name
    scenario_obj = PyDssScenario([scenario_name], controllers=controllers, export_modes=None)
    scenario_obj.serialize(str(scenario_dir))


def add_scenario(
    project_path: str = typer.Argument(..., exists=True),
    scenario_name: str = typer.Option(
        ...,
        "-s",
        "--scenario_name",
        "--scenario-name",
        help="name of the new scenario",
    ),
    controller_mapping: str = typer.Option(
        ...,
        "-c",
        "--controller-mapping",
        exists=True,
        help="JSON file that maps controller type to controller definition files",
    ),
):
    """Add a new scenario to an existing project"""
    build_scenario(project_path, scenario_name, controller_mapping)
