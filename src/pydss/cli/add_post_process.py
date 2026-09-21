"""CLI to create a new pydss project"""


import typer

from pydss.pydss_project import PyDssProject


def add_post_process(
    project_path: str,
    scenario_name: str,
    script: str,
    config_file: str,
):
    """Add post-process script to pydss scenario."""
    project = PyDssProject.load_project(project_path)
    scenario = project.get_scenario(scenario_name)
    pp_info = {"script": script, "config_file": config_file}
    scenario.add_post_process(pp_info)
    project.serialize()
