"""CLI to edit an existing project or scenario"""

import typer

from pydss.common import CONTROLLER_TYPES
from pydss.pydss_project import update_pydss_controllers


edit_scenario = typer.Typer(help="Edit scenario in a pydss project.")


@edit_scenario.callback()
def main(
    project_path: str = typer.Option(..., "-p", "--project-path",
    help="project path",
    ),
    scenario: str = typer.Option(..., "-s", "--scenario",
    help="Project name (should exist)",
    ),
):
    """Edit scenario in a pydss project."""


@edit_scenario.command()
def update_controllers(
    ctx: typer.Context,
    controller: str = typer.Option(..., "-c", "--controller",
    help="controller name",
    ),
    dss_file: str = typer.Option(..., "-f", "--dss-file",
    help="OpenDSS file containing elements",
    ),
    controller_type: str = typer.Option(..., "-t", "--controller-type",
    help="controller type",
    ),
):
    """Update a scenario's controllers from an OpenDSS file."""
    if controller_type not in CONTROLLER_TYPES:
        raise typer.BadParameter(f"must be one of {CONTROLLER_TYPES}")
    project_path = ctx.parent.params["project_path"]
    scenario = ctx.parent.params["scenario"]
    update_pydss_controllers(
        project_path=project_path,
        scenario=scenario,
        controller_type=controller_type,
        controller=controller,
        dss_file=dss_file
    )
