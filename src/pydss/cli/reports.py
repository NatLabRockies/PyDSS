"""
CLI to run a pydss project
"""

import typer
import json
import os

from terminaltables import SingleTable
from os.path import normpath, basename


def reports(
    project_path: str,
    list_reports: bool = typer.Option(
        False,
        "-l",
        "--list-reports",
        help="List all reports for a given project path",
    ),
    index: int = typer.Option(
        0,
        "-i",
        "--index",
        help="View report by index (use -l flag to see list of available reports)",
    ),
    scenario: str | None = typer.Option(
        None,
        "-s",
        "--scenario",
        help="Pydss scenario name.",
    ),
    report: str | None = typer.Option(
        None,
        "-r",
        "--report",
        help="Pydss report name.",
    ),
):
    """Explore and print pydss reports."""
    assert not (list_reports and index), (
        "Both 'list' and 'index' options cannot be set to true at the same time"
    )
    assert os.path.exists(project_path), "The provided project path {} does not exist".format(
        project_path
    )
    logs_path = os.path.join(project_path, "Logs")
    assert os.path.exists(logs_path), "No Logs folder in the provided project path."
    print(logs_path)
    report_list = get_available_reports(logs_path)
    project = basename(normpath(project_path))
    if list_reports:
        table = SingleTable(report_list, title="Available pydss reports")
        print("")
        print(table.table)
    elif index:
        idx, project_name, scenario_name, report_name = report_list[index]
        print_report(logs_path, project_name, scenario_name, report_name)
    elif project:
        for dx, project_name, scenario_name, report_name in report_list[1:]:
            if project_name == project:
                if scenario is None or scenario == scenario_name:
                    if report is None or report == report_name:
                        print_report(logs_path, project_name, scenario_name, report_name)


def print_report(logs_path, project, scenario, report):
    file_name = "{}__{}__reports.log".format(project, scenario)
    file_path = os.path.join(logs_path, file_name)
    assert os.path.exists(file_path), (
        "Report {} for project: {} / scenario: {} does not exist".format(report, project, scenario)
    )

    table_data = []
    keys = {}
    with open(os.path.join(logs_path, file_name), "r") as f:
        for line in f:
            data = json.loads(line.strip())
            if "Report" not in data:
                print("Skipping {}. Not a valid pydss report.".format(file_name))
                return None
            elif data["Report"] == report:
                if report not in keys:
                    keys[report] = list(data.keys())
                    keys[report] = [x for x in keys[report] if x != "Report"]
                values = []
                for k in keys[report]:
                    values.append(data[k])
                table_data.append(values)
    table_data.insert(0, keys[report])
    table = SingleTable(
        table_data, title="{} report (Project: {}, Scenario: {})".format(report, project, scenario)
    )
    print("")
    print(table.table)
    return


def get_available_reports(logs_path):
    log_files = list(filter(lambda x: ".log" in x, os.listdir(logs_path)))
    report_files = [x for x in log_files if "__reports" in x]
    headings = ["#", "Project", "Scenario", "Report"]
    report_list = [headings]
    report_number = 0
    for report in report_files:
        project, scenario, _ = report.split("__")
        print(report_number, project, scenario, report)
        report_types = get_report_types(logs_path, report)
        if report_types is not None:
            for report_type in report_types:
                report_number += 1
                report_list.append([report_number, project, scenario, report_type])
    return report_list


def get_report_types(logs_path, report_file):
    file_name = os.path.join(logs_path, report_file)
    print(file_name)
    f = open(file_name, "r")
    lines = f.readlines()
    report_types = []
    for line in lines:
        data = json.loads(line.strip())
        if "Report" not in data:
            print("Skipping {}. Not a valid pydss report.".format(file_name))
            return None
        else:
            if data["Report"] not in report_types:
                report_types.append(data["Report"])
    return report_types
