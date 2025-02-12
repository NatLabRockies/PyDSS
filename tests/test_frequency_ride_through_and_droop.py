import re
import os
from PyDSS.pydss_project import PyDssProject
from PyDSS.pydss_results import PyDssResults
from tests.common import (
    FREQUENCY_RIDE_THROUGH_AND_DROOP_PATH,
    cleanup_project
)
from PyDSS.common import (SIMULATION_SETTINGS_FILENAME,
                          RUN_SIMULATION_FILENAME,
)
from PyDSS.pydss_fs_interface import STORE_FILENAME

def test_frt_and_droop(cleanup_project):
    PyDssProject.run_project(
        path=FREQUENCY_RIDE_THROUGH_AND_DROOP_PATH,
        simulation_file=SIMULATION_SETTINGS_FILENAME
    )
    results=PyDssResults(FREQUENCY_RIDE_THROUGH_AND_DROOP_PATH)
    scenario_droop=results.scenarios[0]
    scenario_frt=results.scenarios[1]

    kw_df_droop=scenario_droop.get_full_dataframe("Generators", "kW")
    class_df_droop=scenario_droop.get_full_dataframe("Generators", "class")
    kw_df_frt=scenario_frt.get_full_dataframe("Generators", "kW")
    class_df_frt=scenario_frt.get_full_dataframe("Generators", "class")
    
    assert not kw_df_droop[kw_df_droop[kw_df_droop.columns[0]]<=8].empty #check if droop reduces kw below 8 (it should)
    assert 0.0 in kw_df_frt.values #check that DER tripped and active power dropped to 0.0 kW
    assert 1.0 not in class_df_droop.values #check that DER did not trip and class parameter was not changed from 0 to 1
    assert 1.0 in class_df_frt.values #check that DER did trip and class parameter was changed from 0 to 1
