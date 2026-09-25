"""
CLI to run the pydss server
"""

from loguru import logger
import uvicorn
import typer

from pydss.api.server import PydssServer


def serve(
    ip: str = typer.Option("127.0.0.1", hidden=True),
    port: int = typer.Option(
        9090,
        "-p",
        "--port",
        help="Socket port for the server",
    ),
):
    """Run a pydss RESTful API server."""
    logger.level("DEBUG")
    pydss = PydssServer(ip, port)
    uvicorn.run(pydss.app, host=ip, port=port)
