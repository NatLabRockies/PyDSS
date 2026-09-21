"""
CLI to run the pydss server
"""

from loguru import logger
from aiohttp import web
import typer

from pydss.api.server import pydss_server

def serve(
    ip: str = typer.Option("127.0.0.1", hidden=True),
    port: int = typer.Option(9090, "-p", "--port",
    help="Socket port for the server",
    ),
):
    """Run a pydss RESTful API server."""
    FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
    logger.level("DEBUG")
    pydss = pydss_server(ip, port)
    web.run_app(pydss.app, port=port)