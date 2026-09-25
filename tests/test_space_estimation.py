import os


from pydss.pydss_project import PyDssProject


RUN_PROJECT_PATH = os.path.join("tests", "data", "project")


def test_space_estimation_with_dry_run(cleanup_project):
    """Should generate esimated space with dry run simulation"""
    # dry run pydss project
    project = PyDssProject.load_project(RUN_PROJECT_PATH)
    project.run(dry_run=True)

    assert "scenario1" in project.estimated_space
    assert project.estimated_space["scenario1"] is not None
    assert project.estimated_space["scenario1"] > 0
