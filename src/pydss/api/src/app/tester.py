from pathlib import Path
import time
import os

from loguru import logger

from pydss.simulation_input_models import load_simulation_settings
from pydss.api.src.app.data_writer import DataWriter
from pydss.dss_instance import OpenDSS


def run_test(tomlpath):
    try:
        settings = load_simulation_settings(Path(tomlpath))
    except Exception as error:
        logger.error(f"Invalid simulation settings passed, {error}")
        return

    pydss_obj = OpenDSS(settings)
    export_path = os.path.join(pydss_obj._dssPath["Export"], settings.project.active_scenario)
    steps, start_time, end_time = pydss_obj._dssSolver.SimulationSteps()
    writer = DataWriter(export_path, format="json", column_length=steps)

    start_timestamp = time.time()
    for step in range(steps):
        results = pydss_obj.RunStep(step)
        restructured_results = {}
        for k, val in results.items():
            if "." not in k:
                class_name = "Bus"
                elem_name = k
            else:
                class_name, elem_name = k.split(".")

            if class_name not in restructured_results:
                restructured_results[class_name] = {}
            if not isinstance(val, complex):
                restructured_results[class_name][elem_name] = val
        writer.write(
            pydss_obj._Options["Helics"]["Federate name"],
            pydss_obj._dssSolver.GetTotalSeconds(),
            restructured_results,
            step,
        )
    logger.debug("{} seconds".format(time.time() - start_timestamp))
