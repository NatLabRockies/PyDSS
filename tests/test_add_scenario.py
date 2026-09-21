from pathlib import Path
import tempfile
import shutil
import toml
import os

from pydss.cli.add_scenario import build_scenario

PYDSS_PROJECT = Path(__file__).parent / "data" / "project"
MAPPING_FILE = Path(__file__).parent / "data" / "add_scenario" / "controller_map.toml"



def test_add_scenario():
     
    with tempfile.TemporaryDirectory() as tmpdirname:
        tmpdirname_obj = Path(tmpdirname) / "tmp"
        shutil.copytree(PYDSS_PROJECT, str(tmpdirname_obj))
        settings_path = tmpdirname_obj / "simulation.toml"
        settings = toml.load(settings_path)
        settings['Project']['Project Path'] = str(tmpdirname_obj.absolute())
        toml.dump(settings, open(settings_path, "w"))
        build_scenario(str(tmpdirname_obj), "test_scenario", str(MAPPING_FILE))
        assert (tmpdirname_obj / "Scenarios" / "test_scenario").exists()
        assert (tmpdirname_obj / "Scenarios" / "test_scenario" / "pyControllerList" / "MotorStall.toml").exists()
        