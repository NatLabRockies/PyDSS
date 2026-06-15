"""Generates tables of the configuration data models."""

import enum
import inspect
import os
import re
import textwrap
from collections import defaultdict
from pathlib import Path

import click

from pydss import common
from pydss import simulation_input_models
from pydss.simulation_input_models import create_simulation_settings


MODEL_ORDER = (
    "SimulationSettingsModel",
    "ProjectModel",
    "ScenarioModel",
    "ScenarioPostProcessModel",
    "SnapshotTimePointSelectionConfigModel",
    "ExportsModel",
    "FrequencyModel",
    "HelicsModel",
    "LoggingModel",
    "MonteCarloModel",
    "ProfilesModel",
    "ReportsModel",
    "SimulationRangeModel",
    "CapacitorStateChangeCountReportModel",
    "FeederLossesReportModel",
    "PvClippingReportModel",
    "PvCurtailmentReportModel",
    "RegControlTapNumberChangeCountsReportModel",
    "ThermalMetricsReportModel",
    "VoltageMetricsReportModel",
)

ABSTRACT_TYPES = ("InputsBaseModel", "ReportsBaseModel", "ReportBase")


@click.command()
@click.option(
    "-o",
    "--output",
    default="build/model_tables",
    show_default=True,
    help="output directory",
    callback=lambda _, __, x: Path(x),
)
def make_tables(output):
    os.makedirs(output, exist_ok=True)
    ordered_names, classes = get_ordered_class_names()
    all_names = set(ordered_names)
    enum_mapping = make_enum_mapping()
    with open(output / "input_models.rst", "w") as f_rst:
        property_types = parse_property_types(ordered_names, classes)
        for name in ordered_names:
            cls = classes[name]
            schema = cls.model_json_schema()
            if name in ABSTRACT_TYPES:
                continue
            f_rst.write(f".. _{name}:\n\n")
            display_name = name.replace("Model", "")
            f_rst.write(display_name + "\n")
            f_rst.write("=" * len(display_name) + "\n\n")
            f_rst.write(".. csv-table::\n")
            f_rst.write(f"   :file: {name}.csv\n")
            f_rst.write("   :delim: tab\n\n")

            with open(output / (cls.__name__ + ".csv"), "w") as f_csv:
                header = ("Property", "Type", "Description", "Required", "Default")
                f_csv.write("\t".join(header) + "\n")
                required_props = set(schema.get("required", []))
                for prop, vals in schema["properties"].items():
                    if vals.get("internal", False):
                        continue
                    description = format_description(vals["description"])
                    title = vals["title"]
                    type_str = property_types.get(name, {}).get(title)
                    if type_str is not None and type_str in all_names:
                        # This is one of our types and it has a label that we can link to.
                        type_str = f":ref:`{type_str}`"
                    elif type_str in enum_mapping:
                        description = format_enum_description(
                            enum_mapping[type_str], vals["description"]
                        )
                    else:
                        type_str = vals.get("type", "Any")
                    if name == "SimulationSettingsModel":
                        default = ""
                    else:
                        default = str(vals.get("default", ""))
                    row = (
                        title,
                        type_str,
                        f'"{description}"',
                        str(prop in required_props),
                        default,
                    )
                    f_csv.write("\t".join(row))
                    f_csv.write("\n")

    create_simulation_settings(
        output.parent, "ExampleProject", ["scenario1", "scenario2"], force=True
    )
    print(f"Generated simulation settings tables in {output}")


def format_description(description, max_width=70):
    return "\n\n".join(textwrap.wrap(description, width=max_width))


def format_enum_description(cls, description, max_width=70):
    text = [description] + [f"- {x.value}" for x in cls]
    return "\n\n".join(text)


def get_ordered_class_names():
    """Create a list of class names in the order to be written in the RST file.
    Inspect the simulation_input_models module for classes.

    Returns
    -------
    list, dict
        list of class names (str), mapping of class name to Python class

    """

    items = inspect.getmembers(
        simulation_input_models,
        lambda x: inspect.isclass(x)
        and issubclass(x, simulation_input_models.InputsBaseModel),
    )
    classes = {x[0]: x[1] for x in items}
    class_names = set(classes.keys())
    ordered_names = []
    unordered_names = []
    for name in MODEL_ORDER:
        assert name in class_names, name
        ordered_names.append(name)
        class_names.remove(name)
    unordered_names = list(class_names)
    unordered_names.sort()
    ordered_names.extend(unordered_names)
    return ordered_names, classes


def make_enum_mapping():
    """Return a mapping of name to class of all enums in the pydss.common module.

    Returns
    -------
    dict

    """
    return {
        name: cls
        for name, cls in inspect.getmembers(
            common, lambda x: inspect.isclass(x) and issubclass(x, enum.Enum)
        )
    }


def parse_property_types(ordered_names, classes):
    """Find the types of the each class property.

    Returns
    -------
    dict
        Two-level dict: {class_name: {property_name: class}}

    """
    regex_definition = re.compile(r"^#\/(?:definitions|\$defs)\/(\w+)")
    property_types = defaultdict(dict)
    for name in ordered_names:
        if name in ABSTRACT_TYPES:
            continue
        cls = classes[name]
        schema = cls.model_json_schema()
        for prop, vals in schema.get("properties", {}).items():
            title = vals.get("title", prop)
            if "allOf" in vals:
                if len(vals["allOf"]) == 1:
                    match = regex_definition.search(vals["allOf"][0]["$ref"])
                    assert match, vals["allOf"]
                    definition = match.group(1)
                    property_types[name][title] = definition
                else:
                    print(f"WARNING: Possible bug: need handling of %s", vals["allOf"])
    return property_types


if __name__ == "__main__":
    make_tables()
