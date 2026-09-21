"""Main CLI command for pydss."""

from loguru import logger
import typer

from pydss.cli.create_project import create_project
from pydss.cli.add_post_process import add_post_process
from pydss.cli.controllers import controllers
from pydss.cli.convert import convert
from pydss.cli.export import export
from pydss.cli.extract import extract, extract_element_files
from pydss.cli.run import run
from pydss.cli.edit_scenario import edit_scenario

from pydss.cli.reports import reports
from pydss.cli.add_scenario import add_scenario

server_dependencies_installed = True

try:
    from pydss.cli.run_server import serve
except ImportError:
    server_dependencies_installed = False
    logger.warning(
        "Server dependencies not installed. Use 'pip install NREL-pydss[server]' to install additional dependencies"
    )

cli = typer.Typer(help="Pydss commands")


@cli.callback()
def main():
    """Pydss commands"""

cli.command()(create_project)
cli.command()(add_post_process)
cli.command()(export)
cli.command()(extract)
cli.command()(extract_element_files)
cli.command()(run)
cli.command()(add_scenario)
cli.add_typer(edit_scenario, name="edit-scenario")
cli.add_typer(convert, name="convert")
cli.add_typer(controllers, name="controllers")
cli.command()(reports)
if server_dependencies_installed:
    cli.command()(serve)