"""
CLI to add controllers to the local registry
"""

import sys
import os

import typer


from pydss.common import CONTROLLER_TYPES
from pydss.utils.utils import load_data
from pydss.registry import Registry

controllers = typer.Typer(help="Manage registered pydss controllers.")


@controllers.command()
def register(controller_type: str, filename: str):
    """Register a controller in the local registry."""
    if controller_type not in CONTROLLER_TYPES:
        print(f"controller_type must be one of {CONTROLLER_TYPES}")
        sys.exit(1)
    if not os.path.exists(filename):
        print(f"{filename} does not exist")
        sys.exit(1)

    registry = Registry()
    for name in load_data(filename):
        data = {"name": name, "filename": filename}
        registry.register_controller(controller_type, data)
        print(f"Registered {controller_type} {name}")


@controllers.command()
def unregister(controller_type: str, name: str):
    """Unregister a controller."""
    Registry().unregister_controller(controller_type, name)
    print(f"Unregistered {controller_type} {name}")


@controllers.command()
def show():
    """Show the registered controllers."""
    Registry().show_controllers()


@controllers.command()
def reset_defaults():
    """Reset defaults."""
    Registry().reset_defaults(controllers_only=True)
    print("Reset pydss defaults")
