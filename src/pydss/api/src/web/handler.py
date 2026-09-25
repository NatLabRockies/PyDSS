from multiprocessing import Queue, Process, Event, cpu_count
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from datetime import date, datetime
import json
import shutil
import asyncio
import os
import re
import tempfile
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from loguru import logger
from fastapi import Request
from fastapi.responses import JSONResponse
import numpy as np
import pandas as pd

from pydss.pydss_project import PyDssProject, PyDssScenario, ControllerType
from pydss.simulation_input_models import SimulationSettingsModel
from pydss.api.src.web.parser import bytestream_decode
from pydss.api.src.app.pydss import PyDSS
from pydss.pydss_results import PyDssResults, PyDssScenarioResults
from pydss.exceptions import InvalidParameter
from pydss.element_options import ElementOptions


class _ResponseAdapter:
    @staticmethod
    def json_response(data, status=200):
        return JSONResponse(content=data, status_code=status)


web = _ResponseAdapter()


class Handler:
    """Handlers for web server."""

    def __init__(self):
        """Constructor for pydss handler."""

        logger.info("Initializing Handler ....")

        # Initializing pydss_instances dict
        self.pydss_instances = dict()

        # Event flag to control shutdown of background tasks
        self.event = Event()
        logger.info(f"Maximum parallel processes: {cpu_count() - 1}")
        self.pool = ThreadPoolExecutor(max_workers=cpu_count() - 1)

    def start_simulation(self, data):
        parameters = data.get("parameters", {})
        project_path = parameters.get("project_path")
        manifest = None
        if project_path:
            project = PyDssProject.load_project(project_path)
            settings = project.simulation_config
            scenario = parameters.get("scenario")
            if scenario:
                project_scenario = project.get_scenario(scenario)
                settings.project.active_scenario = scenario
            else:
                project_scenario = project.get_scenario(settings.project.active_scenario)
            overrides = parameters.get("settings_overrides", {})
            if overrides:
                settings = SimulationSettingsModel.model_validate(
                    self._merge_settings(settings.model_dump(mode="json"), overrides)
                )
                settings.project.active_scenario = project_scenario.name
            data = dict(data)
            data["project_path"] = project_path
            data["parameters"] = settings.model_dump(mode="json")
        pydss_uuid = str(uuid4())
        if project_path:
            manifest = {
                "id": pydss_uuid,
                "project_path": project_path,
                "project": os.path.basename(os.path.normpath(project_path)),
                "scenario": settings.project.active_scenario,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "status": "starting",
                "effective_settings": data["parameters"],
                "controllers": {
                    controller.value if hasattr(controller, "value") else str(controller): config
                    for controller, config in project_scenario.controllers.items()
                },
                "launch_metadata": parameters.get("run_metadata", {}),
                "events": [],
            }
            self._write_run_manifest(project_path, pydss_uuid, manifest)
        q = Queue()
        process = Process(target=PyDSS, name=pydss_uuid, args=(self.event, q, data))
        self.pydss_instances[pydss_uuid] = {
            "queue": q,
            "process": process,
            "status": "starting",
            "events": [],
            "created_at": datetime.utcnow().isoformat() + "Z",
            "last_event": None,
            "manifest": manifest,
        }
        future = asyncio.get_running_loop().run_in_executor(
            self.pool, self._post_put_background_task, pydss_uuid
        )
        future.add_done_callback(self._post_put_callback)
        process.start()
        return {
            "id": pydss_uuid,
            "status": "starting",
            "message": "Simulation instance is starting",
        }

    @staticmethod
    def _merge_settings(current, updates):
        merged = dict(current)
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = Handler._merge_settings(merged[key], value)
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _run_manifest_filename(project_path, pydss_uuid):
        return os.path.join(project_path, "Runs", f"{pydss_uuid}.json")

    def _write_run_manifest(self, project_path, pydss_uuid, manifest):
        filename = self._run_manifest_filename(project_path, pydss_uuid)
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "w", encoding="utf-8") as file_out:
            json.dump(manifest, file_out, indent=2, default=str)

    def _update_run_manifest(self, instance):
        manifest = instance.get("manifest")
        if manifest is None:
            return
        self._write_run_manifest(manifest["project_path"], manifest["id"], manifest)

    def get_project_runs(self, project_path):
        runs_dir = os.path.join(project_path, "Runs")
        if not os.path.isdir(runs_dir):
            return {"runs": []}
        runs = []
        for filename in sorted(os.listdir(runs_dir), reverse=True):
            if not filename.endswith(".json"):
                continue
            with open(os.path.join(runs_dir, filename), encoding="utf-8") as file_in:
                runs.append(json.load(file_in))
        return {"runs": sorted(runs, key=lambda run: run.get("created_at", ""), reverse=True)}

    def submit_command(self, pydss_uuid, command, parameters):
        instance = self.pydss_instances.get(pydss_uuid)
        if instance is None:
            raise KeyError(f"simulation {pydss_uuid} was not found")
        if not instance["process"].is_alive():
            raise RuntimeError(f"simulation {pydss_uuid} is not running")
        future = asyncio.get_running_loop().run_in_executor(
            self.pool, self._post_put_background_task, pydss_uuid
        )
        future.add_done_callback(self._post_put_callback)
        instance["status"] = "running" if command == "run" else "active"
        if instance.get("manifest") is not None:
            instance["manifest"]["status"] = instance["status"]
            instance["manifest"]["started_at"] = datetime.utcnow().isoformat() + "Z"
            self._update_run_manifest(instance)
        instance["queue"].put({"UUID": pydss_uuid, "command": command, "parameters": parameters})
        return {"id": pydss_uuid, "status": instance["status"], "command": command}

    def stop_simulation(self, pydss_uuid):
        instance = self.pydss_instances.get(pydss_uuid)
        if instance is None:
            raise KeyError(f"simulation {pydss_uuid} was not found")
        instance["status"] = "stopping"
        if instance.get("manifest") is not None:
            instance["manifest"]["status"] = "stopping"
            self._update_run_manifest(instance)
        instance["queue"].put("END")
        return {"id": pydss_uuid, "status": "stopping"}

    def get_simulation_state(self, pydss_uuid):
        instance = self.pydss_instances.get(pydss_uuid)
        if instance is None:
            raise KeyError(f"simulation {pydss_uuid} was not found")
        process = instance["process"]
        status = instance["status"]
        if status == "stopping" and not process.is_alive():
            status = "stopped"
        return {
            "id": pydss_uuid,
            "status": status,
            "alive": process.is_alive(),
            "created_at": instance["created_at"],
            "last_event": instance["last_event"],
            "event_count": len(instance["events"]),
        }

    def get_simulation_event_history(self, pydss_uuid, after=0, limit=100):
        instance = self.pydss_instances.get(pydss_uuid)
        if instance is None:
            raise KeyError(f"simulation {pydss_uuid} was not found")
        events = instance["events"]
        return {
            "id": pydss_uuid,
            "events": events[after : after + limit],
            "next_cursor": min(after + limit, len(events)),
            "total": len(events),
        }

    @staticmethod
    def get_project_details(path):
        project = PyDssProject.load_project(path)
        settings = project.simulation_config
        settings_data = settings.model_dump() if hasattr(settings, "model_dump") else settings.dict()
        return {
            "name": os.path.basename(os.path.normpath(path)),
            "path": project.project_path,
            "settings": settings_data,
            "scenarios": [
                {
                    "name": scenario.name,
                    "controller_types": [
                        controller.value if hasattr(controller, "value") else str(controller)
                        for controller in scenario.controllers
                    ],
                }
                for scenario in project.scenarios
            ],
        }

    @staticmethod
    def get_project_scenario(path, scenario_name):
        project = PyDssProject.load_project(path)
        scenario = project.get_scenario(scenario_name)
        return {
            "project_path": project.project_path,
            "name": scenario.name,
            "controller_types": [
                controller.value if hasattr(controller, "value") else str(controller)
                for controller in scenario.controllers
            ],
            "export_modes": [
                mode.value if hasattr(mode, "value") else str(mode) for mode in scenario.exports
            ],
            "post_process_infos": [
                info.model_dump() if hasattr(info, "model_dump") else info.dict()
                for info in scenario.post_process_infos
            ],
        }

    async def get_pydss_project_info(self, request: Request, path: str):
        """
        ---
        summary: Returns a dictionary of valid project and scenarios in the provided path
        tags:
         - pydss project
        parameters:
         - name: path
           in: query
           required: true
           schema:
              type: string
              example: C:/Users/alatif/Desktop/Pydss_2.0/pydss/examples
        responses:
         '200':
           description: Successfully retrieved project information
           content:
              application/json:
                schema:
                    type: object
                examples:
                    get_instance_status:
                        value:
                            Status: 200
                            Message: pydss instance with the provided UUID is currently running
                            UUID: 96c21e00-cd3c-4943-a914-14451f5f7ab6
                            "Data": {'Project1' : {'Scenario1', 'Scenario2'}, 'Project2' : {'Scenario1'}}
         '406':
           description: Provided path does not exist
           content:
              application/json:
                schema:
                    type: object
                examples:
                    get_instance_status:
                        value:
                            Status: 406
                            Message: Provided path does not exist
                            UUID: None
        """
        logger.info(f"Exploring {path} for valid projects")

        if not os.path.exists(path):
            return web.json_response(
                {"Status": 404, "Message": "Provided path does not exist", "UUID": None}
            )

        subfolders = [f.path for f in os.scandir(path) if f.is_dir()]
        projects = {}
        for folder in subfolders:
            try:
                pydss_project = PyDssProject.load_project(folder)
                projects[pydss_project._name] = [x.name for x in pydss_project.scenarios]
            except Exception:
                pass

        n = len(projects)
        if n > 0:
            return web.json_response(
                {
                    "Status": 200,
                    "Message": f"{n} valid projects found",
                    "UUID": None,
                    "Data": projects,
                }
            )
        else:
            return web.json_response(
                {
                    "Status": 404,
                    "Message": "No valid pydss project in provided base path",
                    "UUID": None,
                }
            )

    async def get_results_metadata(self, request: Request):
        """
        ---
        summary: Return metadata for the completed PyDSS results in a project
        tags:
         - results
        parameters:
         - name: path
           in: query
           required: true
           schema:
              type: string
         - name: scenario
           in: query
           required: false
           schema:
              type: string
        """
        path = request.query_params.get("path")
        if not path:
            return self._api_error("The path query parameter is required", 400)

        try:
            results = self._load_results(path)
            scenarios = results.scenarios
            scenario_name = request.query_params.get("scenario")
            if scenario_name:
                scenarios = [results.get_scenario(scenario_name)]

            data = []
            for scenario in scenarios:
                timestamps = scenario.get_timestamps()
                data.append(
                    {
                        "name": scenario.name,
                        "element_classes": scenario.list_element_classes(),
                        "time_points": len(timestamps),
                        "start": self._json_value(timestamps.iloc[0]) if len(timestamps) else None,
                        "end": self._json_value(timestamps.iloc[-1]) if len(timestamps) else None,
                    }
                )
            return web.json_response({"project_path": path, "scenarios": data})
        except (FileNotFoundError, KeyError, ValueError) as exc:
            return self._api_error(str(exc), 404)
        except Exception as exc:
            logger.exception("Failed to load result metadata for %s", path)
            return self._api_error(str(exc), 500)

    async def get_result_elements(self, request: Request):
        """
        ---
        summary: Return the stored element classes, names, and properties
        tags:
         - results
        parameters:
         - name: path
           in: query
           required: true
           schema:
              type: string
         - name: scenario
           in: query
           required: true
           schema:
              type: string
        """
        path = request.query_params.get("path")
        scenario_name = request.query_params.get("scenario")
        if not path or not scenario_name:
            return self._api_error("The path and scenario query parameters are required", 400)

        try:
            scenario = self._load_results(path).get_scenario(scenario_name)
            elements = {}
            for element_class in scenario.list_element_classes():
                try:
                    summed_properties = scenario.list_summed_element_properties(element_class)
                except InvalidParameter:
                    summed_properties = []
                try:
                    summed_timeseries_properties = scenario.list_summed_element_time_series_properties(
                        element_class
                    )
                except InvalidParameter:
                    summed_timeseries_properties = []
                elements[element_class] = {
                    "names": scenario.list_element_names(element_class),
                    "properties": scenario.list_element_properties(element_class),
                    "summed_properties": summed_properties,
                    "summed_timeseries_properties": summed_timeseries_properties,
                }
            return web.json_response({"scenario": scenario_name, "elements": elements})
        except (FileNotFoundError, KeyError, ValueError) as exc:
            return self._api_error(str(exc), 404)
        except Exception as exc:
            logger.exception("Failed to list result elements for %s", path)
            return self._api_error(str(exc), 404)

    async def get_result_timeseries(self, request: Request):
        """
        ---
        summary: Return a bounded page of timeseries data for one stored element
        tags:
         - results
        parameters:
         - name: path
           in: query
           required: true
           schema:
              type: string
         - name: scenario
           in: query
           required: true
           schema:
              type: string
         - name: element_class
           in: query
           required: true
           schema:
              type: string
         - name: property
           in: query
           required: true
           schema:
              type: string
         - name: element_name
           in: query
           required: true
           schema:
              type: string
         - name: offset
           in: query
           required: false
           schema:
              type: integer
              default: 0
         - name: limit
           in: query
           required: false
           schema:
              type: integer
              default: 1000
        """
        required = ("path", "scenario", "element_class", "property", "element_name")
        missing = [name for name in required if not request.query_params.get(name)]
        if missing:
            return self._api_error(f"Missing query parameters: {', '.join(missing)}", 400)

        try:
            offset = max(0, int(request.query_params.get("offset", 0)))
            limit = min(10000, max(1, int(request.query_params.get("limit", 1000))))
        except ValueError:
            return self._api_error("offset and limit must be integers", 400)

        try:
            results = self._load_results(request.query_params["path"])
            scenario = results.get_scenario(request.query_params["scenario"])
            dataframe = scenario.get_dataframe(
                request.query_params["element_class"],
                request.query_params["property"],
                request.query_params["element_name"],
                real_only=request.query_params.get("real_only", "false").lower() == "true",
                abs_val=request.query_params.get("abs_val", "false").lower() == "true",
            )
            page = dataframe.iloc[offset : offset + limit]
            rows = []
            for index, row in page.iterrows():
                rows.append(
                    {
                        "timestamp": self._json_value(index),
                        "values": {column: self._json_value(value) for column, value in row.items()},
                    }
                )
            return web.json_response(
                {
                    "scenario": scenario.name,
                    "element_class": request.query_params["element_class"],
                    "property": request.query_params["property"],
                    "element_name": request.query_params["element_name"],
                    "columns": list(dataframe.columns),
                    "offset": offset,
                    "limit": limit,
                    "total": len(dataframe),
                    "rows": rows,
                }
            )
        except (FileNotFoundError, KeyError, ValueError) as exc:
            return self._api_error(str(exc), 404)
        except Exception as exc:
            logger.exception("Failed to read result timeseries")
            return self._api_error(str(exc), 404)

    async def get_result_dataset(self, request: Request):
        """Return every stored HDF signal as wide, browser-analysis-ready rows."""
        path = request.query_params.get("path")
        if not path:
            return self._api_error("The path query parameter is required", 400)
        try:
            requested_scenarios = {
                name for name in request.query_params.get("scenarios", "").split(",") if name
            }
            results = self._load_results(path)
            scenarios = [
                scenario for scenario in results.scenarios
                if not requested_scenarios or scenario.name in requested_scenarios
            ]
            rows = []
            fields = {
                "project": {"fid": "project", "name": "Project", "semanticType": "nominal", "analyticType": "dimension"},
                "scenario": {"fid": "scenario", "name": "Stored scenario", "semanticType": "nominal", "analyticType": "dimension"},
                "base_scenario": {"fid": "base_scenario", "name": "Base scenario", "semanticType": "nominal", "analyticType": "dimension"},
                "sample_index": {"fid": "sample_index", "name": "Monte Carlo sample", "semanticType": "quantitative", "analyticType": "dimension"},
                "timestamp": {"fid": "timestamp", "name": "Timestamp", "semanticType": "temporal", "analyticType": "dimension"},
            }
            signal_count = 0
            for scenario in scenarios:
                scenario_rows = None
                match = re.match(r"^(.*)_MC(\d+)$", scenario.name)
                base_scenario = match.group(1) if match else scenario.name
                sample_index = int(match.group(2)) if match else -1
                for element_class in scenario.list_element_classes():
                    for property_name in scenario.list_element_properties(element_class):
                        try:
                            dataframe = scenario.get_full_dataframe(element_class, property_name)
                        except (InvalidParameter, KeyError):
                            continue
                        if dataframe.empty:
                            continue
                        if scenario_rows is None:
                            scenario_rows = [
                                {
                                    "project": os.path.basename(os.path.normpath(path)),
                                    "scenario": scenario.name,
                                    "base_scenario": base_scenario,
                                    "sample_index": sample_index,
                                    "timestamp": self._json_value(timestamp),
                                }
                                for timestamp in dataframe.index
                            ]
                        for column_name in dataframe.columns:
                            field_prefix = f"{element_class} | {property_name} | {column_name}"
                            values = dataframe[column_name].to_numpy()
                            if np.iscomplexobj(values):
                                components = {
                                    "real": np.real(values),
                                    "imaginary": np.imag(values),
                                    "magnitude": np.abs(values),
                                    "angle_degrees": np.angle(values, deg=True),
                                }
                            else:
                                components = {"value": values}
                            for component, component_values in components.items():
                                field_id = f"{field_prefix} | {component}"
                                if field_id not in fields:
                                    signal_count += 1
                                fields[field_id] = {
                                    "fid": field_id,
                                    "name": field_id,
                                    "semanticType": "quantitative",
                                    "analyticType": "measure",
                                }
                                for row, value in zip(scenario_rows, component_values):
                                    row[field_id] = self._json_value(value)
                if scenario_rows:
                    rows.extend(scenario_rows)
            return web.json_response({
                "rows": rows,
                "fields": list(fields.values()),
                "row_count": len(rows),
                "field_count": len(fields),
                "signal_count": signal_count,
                "scenarios": [scenario.name for scenario in scenarios],
                "source": "store.h5",
            })
        except (FileNotFoundError, KeyError, ValueError) as exc:
            return self._api_error(str(exc), 404)
        except Exception as exc:
            logger.exception("Failed to prepare full HDF result dataset")
            return self._api_error(str(exc), 500)

    async def get_result_timeseries_comparison(self, request: Request):
        """Return one bounded result signal for each requested Monte Carlo sample."""
        required = ("path", "scenarios", "element_class", "property", "element_name")
        missing = [name for name in required if not request.query_params.get(name)]
        if missing:
            return self._api_error(f"Missing query parameters: {', '.join(missing)}", 400)
        try:
            limit = min(1000, max(1, int(request.query_params.get("limit", 200))))
            offset = max(0, int(request.query_params.get("offset", 0)))
            scenario_names = [name for name in request.query_params["scenarios"].split(",") if name][:25]
            results = self._load_results(request.query_params["path"])
            series = []
            for scenario_name in scenario_names:
                dataframe = results.get_scenario(scenario_name).get_dataframe(
                    request.query_params["element_class"],
                    request.query_params["property"],
                    request.query_params["element_name"],
                )
                page = dataframe.iloc[offset : offset + limit]
                series.append({
                    "scenario": scenario_name,
                    "rows": [
                        {"timestamp": self._json_value(index), "value": self._json_value(row.iloc[0])}
                        for index, row in page.iterrows()
                    ],
                })
            return web.json_response({"series": series, "limit": limit, "offset": offset})
        except (FileNotFoundError, KeyError, ValueError) as exc:
            return self._api_error(str(exc), 404)
        except Exception as exc:
            logger.exception("Failed to compare result timeseries")
            return self._api_error(str(exc), 404)

    async def get_result_reports(self, request: Request):
        """
        ---
        summary: Return generated report names or one report payload
        tags:
         - results
        parameters:
         - name: path
           in: query
           required: true
           schema:
              type: string
         - name: report
           in: query
           required: false
           schema:
              type: string
        """
        path = request.query_params.get("path")
        if not path:
            return self._api_error("The path query parameter is required", 400)

        try:
            report_name = request.query_params.get("report")
            report_dir = os.path.join(path, "Reports")
            if not report_name and not os.path.isdir(report_dir):
                return web.json_response({"reports": []})
            results = self._load_results(path)
            if not report_name:
                reports = []
                if os.path.isdir(report_dir):
                    reports = sorted(
                        os.path.splitext(filename)[0]
                        for filename in os.listdir(report_dir)
                        if os.path.isfile(os.path.join(report_dir, filename))
                    )
                return web.json_response({"reports": reports})

            report = results.read_report(report_name)
            if isinstance(report, pd.DataFrame):
                payload = {
                    "columns": list(report.columns),
                    "rows": [
                        {column: self._json_value(value) for column, value in row.items()}
                        for _, row in report.iterrows()
                    ],
                }
            else:
                payload = self._json_value(report)
            return web.json_response({"report": report_name, "data": payload})
        except (FileNotFoundError, KeyError, ValueError) as exc:
            return self._api_error(str(exc), 404)
        except Exception as exc:
            logger.exception("Failed to read report %s", report_name)
            return self._api_error(str(exc), 404)

    @staticmethod
    def _load_results(path):
        if not os.path.isdir(path):
            raise FileNotFoundError(f"Project path does not exist: {path}")
        results = PyDssResults(project_path=path)
        stored_scenarios = set(results.hdf_store.get("Exports", {}))
        results._scenarios = [
            scenario for scenario in results.scenarios
            if scenario.name in stored_scenarios and scenario._group is not None
        ]
        sample_names = sorted(name for name in stored_scenarios if "_MC" in name)
        if not sample_names:
            return results

        options = ElementOptions()
        sample_scenarios = []
        for sample_name in sample_names:
            base_name = sample_name.rsplit("_MC", 1)[0]
            metadata = results.project.read_scenario_export_metadata(base_name)
            sample_scenarios.append(
                PyDssScenarioResults(
                    sample_name,
                    results.project_path,
                    results.hdf_store,
                    results._fs_intf,
                    metadata,
                    options,
                )
            )
        results._scenarios = sample_scenarios
        return results

    @staticmethod
    def _api_error(message, status):
        return web.json_response({"error": {"status": status, "message": message}}, status=status)

    @classmethod
    def _json_value(cls, value):
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (datetime, date, pd.Timestamp)):
            return value.isoformat()
        if isinstance(value, np.generic):
            return cls._json_value(value.item())
        if isinstance(value, np.ndarray):
            return [cls._json_value(item) for item in value.tolist()]
        if isinstance(value, complex):
            return str(value)
        if isinstance(value, dict):
            return {str(key): cls._json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_value(item) for item in value]
        return str(value)

    async def post_pydss_create(self, request: Request):
        """
        ---
        summary: Creates a new project for pydss (User uploads a zipped OpenDSS model)
        tags:
         - pydss project
        requestBody:
            content:
                multipart/form-data:
                    schema:
                      type: object
                      properties:
                        master_file:
                          type: string
                          example: Master_Spohn_existing_VV.dss
                        project:
                          type: string
                          example: test_project
                        scenarios:
                          type: string
                          description: comma separated list of pydss scenarios to be created
                          example: base_case,pv_scenario
                        controller_types:
                          type: string
                          description: comma separated list of pydss controller names
                          example: PvController,StorageController
                        fileName:
                          type: string
                          format: binary
        responses:
         '200':
           description: Successfully retrieved project information
           content:
              application/json:
                schema:
                    type: object
                examples:
                    get_instance_status:
                        value:
                            Status: 200
                            Message: pydss project created
                            UUID: None
         '403':
           description: Provided path does not exist
           content:
              application/json:
                schema:
                    type: object
                examples:
                    get_instance_status:
                        value:
                            Status: 403
                            Message: User does not have access to delete folders
                            UUID: None
        """

        from zipfile import ZipFile

        examples_path = os.path.join("C:/Users/alatif/Desktop/Pydss_2.0/pydss/", "examples")
        unzip_path = os.path.join(examples_path, "uploaded_opendss_project")
        zip_path = os.path.join(examples_path, "uploaded_opendss_project.zip")

        data = None
        with open(zip_path, "wb") as fd:
            while True:
                chunk = await request.content.read(1024)
                if data is None:
                    data = chunk
                else:
                    data += chunk
                if not chunk:
                    break
                fd.write(chunk)

        data = bytestream_decode(data)
        os.makedirs(unzip_path, exist_ok=True)
        with ZipFile(zip_path, "r") as zip_object:
            zip_object.extractall(path=unzip_path)

        controller_types = [ControllerType(x) for x in data["controller_types"].split(",")]

        scenarios = [
            PyDssScenario(
                name=x.strip(),
                controller_types=controller_types,
            )
            for x in data["scenarios"].split(",")
        ]

        PyDssProject.create_project(
            path=examples_path,
            name=data["project"],
            scenarios=scenarios,
            opendss_project_folder=unzip_path,
            master_dss_file=data["master_file"],
        )

        try:
            shutil.rmtree(unzip_path)
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except Exception:
            return web.json_response(
                {
                    "Status": 403,
                    "Message": "User does not have access to delete folders",
                    "UUID": None,
                }
            )

        result = {"Status": 200, "Message": "Pydss project created", "UUID": None}

        # name, scenarios, simulation_config = None, options = None,
        # simulation_file = SIMULATION_SETTINGS_FILENAME, opendss_project_folder = None,
        # master_dss_file = OPENDSS_MASTER_FILENAME

        return web.json_response(result)

    def create_project_from_upload(
        self,
        archive: bytes,
        project_root: str,
        project: str,
        scenarios: str,
        controller_types: str,
        master_file: str,
    ):
        """Create a project from an uploaded OpenDSS zip archive."""
        project_name = Path(project).name
        if not project_name or project_name != project:
            raise ValueError("project must be a simple directory name")

        destination = Path(project_root).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        project_directory = destination / project_name
        if project_directory.exists():
            raise FileExistsError(f"project already exists: {project_name}")

        controller_names = [name.strip() for name in controller_types.split(",") if name.strip()]
        scenario_names = [name.strip() for name in scenarios.split(",") if name.strip()]
        if not scenario_names:
            raise ValueError("at least one scenario is required")

        try:
            controllers = [ControllerType(name) for name in controller_names]
        except ValueError as exc:
            raise ValueError(f"invalid controller type: {exc}") from exc

        with tempfile.TemporaryDirectory(prefix="pydss-upload-") as temporary_directory:
            archive_path = Path(temporary_directory) / "project.zip"
            extract_path = Path(temporary_directory) / "project"
            archive_path.write_bytes(archive)
            try:
                with ZipFile(archive_path) as zip_file:
                    extract_root = extract_path.resolve()
                    for member in zip_file.infolist():
                        member_path = (extract_root / member.filename).resolve()
                        if os.path.commonpath((extract_root, member_path)) != str(extract_root):
                            raise ValueError("zip archive contains an unsafe path")
                    zip_file.extractall(extract_root)
            except BadZipFile as exc:
                raise ValueError("uploaded file is not a valid zip archive") from exc

            project_instance = PyDssProject.create_project(
                path=str(destination),
                name=project_name,
                scenarios=[
                    PyDssScenario(name=name, controller_types=controllers)
                    for name in scenario_names
                ],
                opendss_project_folder=str(extract_path),
                master_dss_file=master_file,
            )

        return {
            "Status": 200,
            "Message": "Pydss project created",
            "UUID": None,
            "project_path": project_instance.project_path,
            "scenarios": scenario_names,
        }

    async def post_pydss_project(self, request: Request):
        return

    async def get_pydss_project(self, request: Request):
        return

    async def post_pydss(self, request: Request):
        """
        ---
        summary: Creates an instance of pydss and runs the simulation
        tags:
         - Simulation
        requestBody:
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            parameters:
                              type: object
                    examples:
                            Example 1:
                                value:
                                    parameters:
                                        Start Year: 2017
                                        Start Day: 1
                                        Start Time (min): 0
                                        End Day: 1
                                        End Time (min): 1439
                                        Date offset: 0
                                        Step resolution (sec): 900
                                        Max Control Iterations: 50
                                        Error tolerance: 0.001
                                        Control mode: Static
                                        Simulation Type: QSTS
                                        Project Path: "C:/Users/alatif/Desktop/Pydss_2.0/pydss/examples"
                                        Active Project: custom_contols
                                        Active Scenario: base_case
                                        DSS File: Master_Spohn_existing_VV.dss
                                        Co-simulation Mode: false
                                        Log Results: false
                                        Export Data Tables: true
                                        Export Data In Memory: true
                                        Federate name: Pydss_x
        responses:
         '200':
           description: Successfully retrieved project information
           content:
              application/json:
                schema:
                    type: object
                examples:
                    get_instance_status:
                        value:
                            Status: 200
                            Message: Starting a pydss instance
                            UUID: 96c21e00-cd3c-4943-a914-14451f5f7ab6
         '500':
           description: Provided path does not exist
           content:
              application/json:
                schema:
                    type: object
                examples:
                    get_instance_status:
                        value:
                            Status: 500
                            Message: Failed to create a pydss instance
                            UUID: None
        """
        data = await request.json()
        logger.info(f"Running command :{data}")
        result = self.start_simulation(data)
        return web.json_response({"Status": 200, "Message": result["message"], "UUID": result["id"]})

    async def put_pydss(self, request: Request):
        (
            """ Running pydss app"""
            """
        ---
        summary: Run a command on an active instance of Pydss
        tags:
         - Simulation

        requestBody:
            content:
                application/json:
                    schema:
                      type: object
                      properties:
                        uuid:
                          type: string
                          format: UUID
                          example: 96c21e00-cd3c-4943-a914-14451f5f7ab6
                        command:
                          type: string
                          example: initialize
                        parameters:
                          type: object
                    examples:
                        Example_1:
                            value:
                                UUID : 96c21e00-cd3c-4943-a914-14451f5f7ab6
                                command: run
                                parameters: {}
        responses:
         '200':
           description: Successfully retrieved project information
           content:
              application/json:
                schema:
                    type: object
                examples:
                    get_instance_status:
                        value:
                            Status: 200
                            Message: Command submitted, awaiting response 
                            UUID: 96c21e00-cd3c-4943-a914-14451f5f7ab6
         '401':
           description: Provided path does not exist
           content:
              application/json:
                schema:
                    type: object
                examples:
                    get_instance_status:
                        value:
                            Status: 401
                            Message: Please provide a command and parameters
                            UUID: None
         '403':
           description: Provided path does not exist
           content:
              application/json:
                schema:
                    type: object
                examples:
                    get_instance_status:
                        value:
                            Status: 403
                            Message: Provided UUID is not valid pydss instance id
                            UUID: None
        """
        )

        data = await request.json()
        logger.info(f"Running command :{data}")

        if "command" not in data or "parameters" not in data:
            msg = "Please provide a command and parameters"
            logger.error(msg)
            return web.json_response({"Status": 401, "Message": msg, "UUID": None})

        pydss_uuid = await self._get_uuid(data=data)

        if pydss_uuid:
            logger.info(f"Running command {data['command']} on pydss instance {pydss_uuid}")
            pydss_t = asyncio.get_running_loop().run_in_executor(
                self.pool, self._post_put_background_task, pydss_uuid
            )
            pydss_t.add_done_callback(self._post_put_callback)

            self.pydss_instances[pydss_uuid]["queue"].put(data)

            result = {
                "Status": 200,
                "Message": f"{data['command']} command submitted, awaiting response ",
                "UUID": pydss_uuid,
            }
            return web.json_response(result)
        else:
            logger.error(f"UUID={pydss_uuid} not found.")

            result = {
                "Status": 403,
                "Message": f"{pydss_uuid} is not valid pydss instance id ",
                "UUID": pydss_uuid,
            }
            return web.json_response(result)

    async def delete_pydss(self, request: Request):
        """
        ---
        summary: Deletes an active instance of Pydss
        tags:
         - Simulation
        parameters:
          - name: uuid
            in: path
            required: true
            schema:
              type: string
              format: uuid
              example: 96c21e00-cd3c-4943-a914-14451f5f7ab6
        responses:
         '200':
           description: Successfully retrieved project information
           content:
              application/json:
                schema:
                    type: object
                examples:
                    get_instance_status:
                        value:
                            Status: 200
                            Message: Successfully deleted a pydss instance
                            UUID: 96c21e00-cd3c-4943-a914-14451f5f7ab6
         '403':
           description: Provided path does not exist
           content:
              application/json:
                schema:
                    type: object
                examples:
                    get_instance_status:
                        value:
                            Status: 403
                            Message: Error closing pydss instance
                            UUID: None
        """

        data = await request.json()
        logger.info(f"Close request submitted: {data}")

        if "UUID" in data:
            pydss_uuid = data["UUID"]

            if pydss_uuid not in self.pydss_instances.keys():
                logger.error(f"UUID={pydss_uuid} not found.")

            try:
                pydss_t = asyncio.get_running_loop().run_in_executor(
                    self.pool, self._delete_background_task, pydss_uuid
                )
                pydss_t.add_done_callback(self._delete_callback)

                self.pydss_instances[pydss_uuid]["queue"].put("END")

                return web.json_response(
                    {
                        "Status": 200,
                        "Message": "Successfully deleted a pydss instance",
                        "UUID": pydss_uuid,
                    }
                )
            except Exception:
                logger.error(f"Error closing pydss instance {pydss_uuid}")
        else:
            return web.json_response(
                {"Status": 403, "Message": "Error closing pydss instance", "UUID": None}
            )

    async def get_instance_uuids(self, request: Request):
        """
        ---
        summary: Returns UUIDs of all the instances currently running on the server
        tags:
         - simulation status
        responses:
         '200':
           description: UUIDs of all currently running pydss instances have been returned
           content:
              application/json:
                schema:
                    type: object
                examples:
                    get_instance_status:
                        value:
                            Status: 200
                            Message: 2 pydss instances currently running
                            UUID: []
         '204':
           description: No active pydss instance found
           content:
              application/json:
                schema:
                    type: object
                examples:
                    get_instance_status:
                        value:
                            Status: 204
                            Message: No pydss instance currently running
                            UUID: ["96c21e00-cd3c-4943-a914-14451f5f7ab6", "96c21e045-cd6c-8394-a914-14451f5f7ab6"]
        """
        uuids = [str(k) for k in self.pydss_instances.keys()]
        if len(uuids) > 0:
            return web.json_response(
                {
                    "Status": 200,
                    "Message": f"{len(uuids)} instances currently running",
                    "Instances": uuids,
                }
            )
        else:
            return web.json_response(
                {
                    "Status": 204,
                    "Message": "No pydss instance currently running",
                    "Instances": uuids,
                }
            )

    async def get_instance_status(self, request: Request, uuid: str):
        """
        ---
        summary: Returns states of process of with UUID matching the passed UUID
        tags:
         - simulation status
        parameters:
          - name: uuid
            in: path
            required: true
            schema:
              type: string
              format: uuid
              example: 96c21e00-cd3c-4943-a914-14451f5f7ab6
        responses:
         '200':
           description: pydss instance with the provided UUID is currently running
           content:
              application/json:
                schema:
                    type: object
                examples:
                    get_instance_status:
                        value:
                            Status: 200
                            Message: pydss instance with the provided UUID is currently running
                            UUID: 96c21e00-cd3c-4943-a914-14451f5f7ab6
         '204':
           description: pydss instance with the provided UUID does not exist
           content:
              application/json:
                schema:
                    type: object
                examples:
                    get_instance_status:
                        value:
                            Status: 204
                            Message: pydss instance with the provided UUID does not exist
                            UUID: None
        """

        if uuid not in self.pydss_instances:
            status = "204"
            msg = "Pydss instance with the provided UUID does not exist"
        else:
            status = "200"
            msg = "Pydss instance with the provided UUID is currently running"

        return web.json_response({"Status": status, "Message": msg, "UUID": uuid})

    def _post_put_background_task(self, pydss_uuid):

        q = self.pydss_instances[pydss_uuid]["queue"]
        result = q.get()
        self._record_event(pydss_uuid, result)
        return result

    def _record_event(self, pydss_uuid, result):
        instance = self.pydss_instances.get(pydss_uuid)
        if instance is None:
            return
        event = {
            "sequence": len(instance["events"]),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "payload": result,
        }
        instance["events"].append(event)
        instance["last_event"] = event
        if isinstance(result, dict):
            status = result.get("Status")
            if status is not None and int(status) >= 400:
                instance["status"] = "failed"
            elif result.get("Message", "").lower().endswith("complete..."):
                instance["status"] = "completed"
            elif instance["status"] == "starting":
                instance["status"] = "ready"
        if instance.get("manifest") is not None:
            instance["manifest"]["status"] = instance["status"]
            instance["manifest"]["events"] = instance["events"]
            if instance["status"] in {"completed", "failed"}:
                instance["manifest"]["finished_at"] = event["timestamp"]
            self._update_run_manifest(instance)

    def _post_put_callback(self, return_value):

        logger.info(f"{return_value.result()}")

    async def _get_uuid(self, data):

        if "UUID" not in data:
            return None

        pydss_uuid = data["UUID"]
        if pydss_uuid not in self.pydss_instances.keys():
            return None

        return pydss_uuid

    def _delete_background_task(self, pydss_uuid):

        while self.pydss_instances[pydss_uuid]["process"].is_alive():
            continue

        del self.pydss_instances[pydss_uuid]

        return {"Status": "Success", "Message": "Pydss instance closed", "UUID": pydss_uuid}

    def _delete_callback(self, return_value):
        logger.info(f"{return_value.result()}")
