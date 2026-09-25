import opendssdirect as dss

from pydss.dss_transformer import DssTransformer
from pydss.dss_element import DssElement


def create_dss_element(element_class, element_name, dss_instance=None):
    """Instantiate the correct class for the given element_class and element_name."""
    if dss_instance is None:
        dss_instance = dss
    if element_class in {"Transformer", "Transformers"}:
        return DssTransformer(dss_instance)
    else:
        return DssElement(dss_instance)
