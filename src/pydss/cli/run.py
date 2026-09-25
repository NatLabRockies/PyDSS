"""
CLI to run a pydss project
"""

from pathlib import Path
import ast
import sys

from loguru import logger
import typer

from pydss.utils.utils import get_cli_string, make_human_readable_size
from pydss.common import SIMULATION_SETTINGS_FILENAME
from pydss.pydss_project import PyDssProject


def run(
    project_path: str = typer.Argument(..., exists=True),
    options: str | None = typer.Option(
        None,
        "-o",
        "--options",
        help="dict-formatted simulation settings that override the config file. "
        'Example:  pydss run ./project --options "{\\"Exports\\": {\\"Export Compression\\": \\"true\\"}}"',
    ),
    simulations_file: str = typer.Option(
        SIMULATION_SETTINGS_FILENAME,
        "-s",
        "--simulations-file",
        help="scenario toml file to run (over rides default)",
    ),
    tar_project: bool = typer.Option(
        False, "-t", "--tar-project", help="Tar project files after successful execution."
    ),
    zip_project: bool = typer.Option(
        False, "-z", "--zip-project", help="Zip project files after successful execution."
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose log output."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Dry run for getting estimated space."),
):
    """Run a pydss simulation."""
    project_path = Path(project_path)
    settings = PyDssProject.load_simulation_settings(project_path, simulations_file)
    if verbose:
        # Override the config file.
        settings.logging.logging_level = "DEBUG"

    filename = None
    console_level = "INFO"
    if not settings.logging.enable_console:
        console_level = "ERROR"
    if verbose:
        console_level = "DEBUG"
    if settings.logging.enable_file:
        logs_path = project_path / "Logs"
        if not logs_path.exists():
            logger.error("Logs path %s does not exist", logs_path)
            sys.exit(1)
        filename = logs_path / "pydss.log"

    logger.level(console_level)
    if filename:
        logger.add(filename)

    logger.info(
        f"CLI: [{get_cli_string()}]",
    )

    if options is not None:
        options = ast.literal_eval(options)
        if not isinstance(options, dict):
            logger.error("options are invalid: %s", options)
            sys.exit(1)

    project = PyDssProject.load_project(
        project_path, options=options, simulation_file=simulations_file
    )
    project.run(tar_project=tar_project, zip_project=zip_project, dry_run=dry_run)

    if dry_run:
        maxlen = max([len(k) for k in project.estimated_space.keys()])
        if len("ScenarioName") > maxlen:
            maxlen = len("ScenarioName")
        template = "{:<{width}}   {}\n".format("ScenarioName", "EstimatedSpace", width=maxlen)

        total_size = 0
        for k, v in project.estimated_space.items():
            total_size += v
            vstr = make_human_readable_size(v)
            template += "{:<{width}} : {}\n".format(k, vstr, width=maxlen)
        template = template.strip()
        logger.info(template)
        logger.info("-" * 30)
        logger.info(f"TotalSpace: {make_human_readable_size(total_size)}")
        logger.info("=" * 30)
        logger.info("Note: compression may reduce the size by ~90% depending on the data.")
