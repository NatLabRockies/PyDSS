"""
CLI to export data from a pydss project
"""

import sys
import os

from loguru import logger
import typer


from pydss.pydss_results import PyDssResults
from pydss.utils.utils import get_cli_string


# TODO Make command to list scenarios.


def export(
    project_path: str,
    fmt: str = typer.Option("csv", "-f", "--fmt", help="Output file format (csv or h5)."),
    compress: bool = typer.Option(
        False,
        "-c",
        "--compress",
        help="Compress output files.",
    ),
    output_dir: str | None = typer.Option(
        None,
        "-o",
        "--output-dir",
        help="Output directory. Default is project exports directory.",
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose log output."),
):
    """Export data from a pydss project."""
    if not os.path.exists(project_path):
        sys.exit(1)

    filename = "pydss_export.log"
    console_level = "INFO"
    if verbose:
        console_level = "DEBUG"

    logger.level(console_level)
    if filename:
        logger.add(filename)

    logger.info("CLI: [%s]", get_cli_string())

    results = PyDssResults(project_path)
    for scenario in results.scenarios:
        scenario.export_data(output_dir, fmt=fmt, compress=compress)
