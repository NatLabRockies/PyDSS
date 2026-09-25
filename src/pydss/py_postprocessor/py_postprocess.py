from pydss.py_postprocessor.postprocess_scripts.derms_optimizer import DermsOptimizer
from pydss.py_postprocessor.postprocess_scripts.ed_li_fo_control import EdLifoControl


POST_PROCESSES = {
    "DERMSOptimizer": DermsOptimizer,
    "EdLiFoControl": EdLifoControl,
    "derms_optimizer": DermsOptimizer,
    "ed_li_fo_control": EdLifoControl,
}


def create(
    project,
    scenario,
    pp_info,
    dss_instance,
    dss_solver,
    dss_objects,
    dss_objects_by_class,
    simulation_settings,
    logger,
):
    script_name = pp_info.script
    assert script_name in POST_PROCESSES, (
        f"Definition for '{script_name}' post process script not found. \n"
        "Please define the controller in PyDSS/py_postprocessor/postprocess_scripts"
    )
    post_processor = POST_PROCESSES[script_name](
        project,
        scenario,
        pp_info,
        dss_instance,
        dss_solver,
        dss_objects,
        dss_objects_by_class,
        simulation_settings,
        logger,
    )
    return post_processor
