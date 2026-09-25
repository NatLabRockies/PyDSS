"""CLI to create a new pydss project"""

import typer
import ast
import sys

from loguru import logger

from pydss.pydss_project import PyDssProject, PyDssScenario, ControllerType, ExportMode


def create_project(
    path: str = typer.Option(
        ...,
        "-P",
        "--path",
        help="path in which to create project",
    ),
    project: str = typer.Option(
        ...,
        "-p",
        "--project",
        help="project name",
    ),
    scenarios: str = typer.Option(
        ...,
        "-s",
        "--scenarios",
        help="comma-delimited scenario names",
    ),
    simulation_file: str = typer.Option(
        "simulation.toml",
        "-f",
        "--simulation-file",
        help="simulation file name",
    ),
    opendss_project_folder: str | None = typer.Option(
        None,
        "-F",
        "--opendss-project-folder",
        exists=True,
        help="simulation file name",
    ),
    master_dss_file: str | None = typer.Option(
        None,
        "-m",
        "--master-dss-file",
        help="simulation file name",
    ),
    simulation_config: str | None = typer.Option(
        None,
        "-S",
        "--simulation-config",
        exists=True,
        help="simulation configuration settings",
    ),
    controller_types: str | None = typer.Option(
        None,
        "-c",
        "--controller-types",
        help="comma-delimited list of controller types",
    ),
    export_modes: str | None = typer.Option(
        None,
        "-e",
        "--export-modes",
        help="comma-delimited list of export modes",
    ),
    options: str | None = typer.Option(
        None,
        "-o",
        "--options",
        help="dict-formatted simulation settings that override the config file. "
        'Example:  pydss run ./project --options "{\\"Simulation Type\\": \\"QSTS\\"}"',
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite directory if it already exists.",
    ),
):
    """Create pydss project."""
    if controller_types is not None:
        controller_types = [ControllerType(x) for x in controller_types.split(",")]
    if export_modes is not None:
        export_modes = [ExportMode(x) for x in export_modes.split(",")]

    if options is not None:
        options = ast.literal_eval(options)
        if not isinstance(options, dict):
            logger.error(f"options must be of type dict; received {type(options)}")
            sys.exit(1)

    scenarios = [
        PyDssScenario(
            name=x.strip(),
            controller_types=controller_types,
            export_modes=export_modes,
        )
        for x in scenarios.split(",")
    ]
    PyDssProject.create_project(
        path,
        project,
        scenarios,
        simulation_config,
        options=options,
        simulation_file=simulation_file,
        master_dss_file=master_dss_file,
        opendss_project_folder=opendss_project_folder,
        force=force,
    )
