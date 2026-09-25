from contextlib import asynccontextmanager
import os

import h5py

from fastapi import FastAPI, Body, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from loguru import logger
import pydss

from pydss.api.src.web.handler import Handler
from pydss.pydss_project import PyDssProject
from pydss.pydss_fs_interface import STORE_FILENAME
from pydss.common import (
    ControllerType,
    DEFAULT_EXPORT_BY_CLASS_SETTINGS_FILE,
    DEFAULT_SUBSCRIPTIONS_FILE,
    EXPORT_BY_CLASS_FILENAME,
    MONTE_CARLO_SETTINGS_FILENAME,
    SUBSCRIPTIONS_FILENAME,
    filename_from_enum,
)
from pydss.helics_interface import Subscription
from pydss.simulation_input_models import SimulationSettingsModel, dump_settings
from pydss.utils.utils import dump_data, load_data


def find_version():
    return pydss.__version__


class SimulationStartRequest(BaseModel):
    parameters: dict = Field(default_factory=dict)


class SimulationCommandRequest(BaseModel):
    command: str = Field(min_length=1)
    parameters: dict = Field(default_factory=dict)


class PydssServer:
    def __init__(self, host, port):
        self.handler = Handler()
        self.app = FastAPI(
            title="Pydss RESTful API documentation",
            version=find_version(),
            description="The API enables creating pydss instances, running simulations and creation of new projects.",
            lifespan=self.lifespan,
        )
        origins = os.environ.get(
            "PYDSS_CORS_ORIGINS",
            "http://localhost:8080,http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=[origin.strip() for origin in origins if origin.strip()],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.add_routes()

    @asynccontextmanager
    async def lifespan(self, app):
        yield
        logger.info("Cleaning up PyDSS API background tasks")
        self.handler.event.set()
        self.handler.pool.shutdown(wait=False, cancel_futures=True)

    def add_routes(self):
        self.app.get("/simulators/pydss/instances")(self.handler.get_instance_uuids)
        self.app.get("/simulators/pydss/status/uuid/{uuid}")(self.handler.get_instance_status)
        self.app.get("/simulators/pydss/info")(self.handler.get_pydss_project_info)
        self.app.get("/api/v1/results/metadata")(self.handler.get_results_metadata)
        self.app.get("/api/v1/results/elements")(self.handler.get_result_elements)
        self.app.get("/api/v1/results/timeseries")(self.handler.get_result_timeseries)
        self.app.get("/api/v1/results/dataset")(self.handler.get_result_dataset)
        self.app.get("/api/v1/results/timeseries/compare")(self.handler.get_result_timeseries_comparison)
        self.app.get("/api/v1/results/reports")(self.handler.get_result_reports)
        self.app.get("/api/v1/results/artifacts")(self.get_result_artifacts)
        self.app.get("/api/v1/results/artifacts/file")(self.get_result_artifact_file)
        self.app.get("/api/v1/projects/details")(self.get_project_details)
        self.app.get("/api/v1/projects/runs")(self.get_project_runs)
        self.app.get("/api/v1/projects/configuration")(self.get_project_configuration)
        self.app.post("/api/v1/projects/configuration/validate")(self.validate_project_configuration)
        self.app.put("/api/v1/projects/configuration")(self.save_project_configuration)
        self.app.get("/api/v1/projects/subscriptions")(self.get_project_subscriptions)
        self.app.put("/api/v1/projects/subscriptions")(self.save_project_subscriptions)
        self.app.get("/api/v1/projects/publications")(self.get_project_publications)
        self.app.put("/api/v1/projects/publications")(self.save_project_publications)
        self.app.get("/api/v1/projects/monte-carlo")(self.get_project_monte_carlo)
        self.app.get("/api/v1/projects/scenarios/{scenario_name}/controllers")(self.get_scenario_controllers)
        self.app.put("/api/v1/projects/scenarios/{scenario_name}/controllers")(self.save_scenario_controllers)
        self.app.get("/api/v1/projects/scenarios/{scenario_name}")(self.get_project_scenario)
        self.app.post("/api/v1/simulations")(self.start_simulation)
        self.app.get("/api/v1/simulations/{uuid}")(self.get_simulation)
        self.app.get("/api/v1/simulations/{uuid}/events")(self.get_simulation_events)
        self.app.post("/api/v1/simulations/{uuid}/commands")(self.submit_simulation_command)
        self.app.delete("/api/v1/simulations/{uuid}")(self.stop_simulation)
        self.app.put("/simulators/pydss")(self.handler.put_pydss)
        self.app.post("/simulators/pydss")(self.handler.post_pydss)
        self.app.post("/simulators/pydss/create")(self.create_project)
        self.app.delete("/simulators/pydss")(self.handler.delete_pydss)

    async def get_project_details(self, path: str = Query(..., description="Project directory")):
        try:
            return self.handler.get_project_details(path)
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def get_project_runs(self, path: str = Query(..., description="Project directory")):
        try:
            if not os.path.isdir(path):
                raise FileNotFoundError(path)
            return self.handler.get_project_runs(path)
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @staticmethod
    def _load_settings(path: str):
        project = PyDssProject.load_project(path)
        return project, project.simulation_config

    async def get_project_configuration(self, path: str = Query(..., description="Project directory")):
        try:
            project, settings = self._load_settings(path)
            return {
                "project_path": project.project_path,
                "settings": settings.model_dump(mode="json", by_alias=False),
            }
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @staticmethod
    def _artifact_files(path):
        root = os.path.realpath(path)
        if not os.path.isdir(root):
            raise FileNotFoundError(f"Project path does not exist: {path}")

        directories = [os.path.join(root, "Reports")]
        for current_root, directory_names, _ in os.walk(root):
            directory_names[:] = [name for name in directory_names if name not in {".git", "Exports"}]
            if os.path.basename(current_root) == "OpenMDAOReports":
                directories.append(current_root)

        files = []
        for directory in directories:
            if not os.path.isdir(directory):
                continue
            for current_root, _, filenames in os.walk(directory):
                for filename in filenames:
                    absolute_path = os.path.realpath(os.path.join(current_root, filename))
                    extension = os.path.splitext(filename)[1].lower()
                    kind = "file"
                    if extension in {".html", ".htm"}:
                        kind = "html"
                    elif extension in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                        kind = "image"
                    files.append({
                        "name": filename,
                        "path": os.path.relpath(absolute_path, root),
                        "kind": kind,
                        "size": os.path.getsize(absolute_path),
                    })
        return sorted(files, key=lambda item: item["path"])

    async def get_result_artifacts(self, path: str = Query(..., description="Project directory")):
        try:
            return {"artifacts": self._artifact_files(path)}
        except (FileNotFoundError, OSError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def get_result_artifact_file(
        self,
        path: str = Query(..., description="Project directory"),
        artifact: str = Query(..., min_length=1, description="Artifact path relative to the project"),
    ):
        try:
            root = os.path.realpath(path)
            filename = os.path.realpath(os.path.join(root, artifact))
            if os.path.commonpath((root, filename)) != root or not os.path.isfile(filename):
                raise FileNotFoundError(artifact)
            allowed = {item["path"] for item in self._artifact_files(root)}
            if artifact not in allowed:
                raise FileNotFoundError(artifact)
            return FileResponse(filename)
        except (FileNotFoundError, OSError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @staticmethod
    def _merge_settings(current, updates):
        merged = dict(current)
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = PydssServer._merge_settings(merged[key], value)
            else:
                merged[key] = value
        return merged

    async def validate_project_configuration(self, payload: dict = Body(...)):
        try:
            path = payload["path"]
            _, current = self._load_settings(path)
            updates = payload.get("settings", {})
            settings = SimulationSettingsModel.model_validate(
                self._merge_settings(current.model_dump(mode="json", by_alias=False), updates)
            )
            return {"valid": True, "settings": settings.model_dump(mode="json", by_alias=False)}
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"Missing field: {exc.args[0]}") from exc
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def save_project_configuration(self, payload: dict = Body(...)):
        try:
            path = payload["path"]
            project, current = self._load_settings(path)
            updates = payload.get("settings", {})
            settings = SimulationSettingsModel.model_validate(
                self._merge_settings(current.model_dump(mode="json", by_alias=False), updates)
            )
            filename = os.path.join(project.project_path, "simulation.toml")
            dump_settings(settings, filename)
            return {
                "saved": True,
                "path": filename,
                "settings": settings.model_dump(mode="json", by_alias=False),
            }
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"Missing field: {exc.args[0]}") from exc
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @staticmethod
    def _subscriptions_filename(path):
        filename = os.path.join(path, "ExportLists", SUBSCRIPTIONS_FILENAME)
        return filename if os.path.exists(filename) else DEFAULT_SUBSCRIPTIONS_FILE

    async def get_project_subscriptions(self, path: str = Query(..., description="Project directory")):
        try:
            filename = self._subscriptions_filename(path)
            data = load_data(filename)
            return {"path": filename, "subscriptions": data.get("subscriptions", [])}
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def save_project_subscriptions(self, payload: dict = Body(...)):
        try:
            path = payload["path"]
            if not os.path.isdir(path):
                raise FileNotFoundError(path)
            subscriptions = []
            for item in payload.get("subscriptions", []):
                model = Subscription.model_validate(item)
                subscriptions.append(
                    model.model_dump(mode="json", exclude={"object", "sub"})
                )
            filename = os.path.join(path, "ExportLists", SUBSCRIPTIONS_FILENAME)
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            dump_data({"subscriptions": subscriptions}, filename)
            return {"saved": True, "path": filename, "subscriptions": subscriptions}
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"Missing field: {exc.args[0]}") from exc
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @staticmethod
    def _publications_filename(path):
        filename = os.path.join(path, "ExportLists", EXPORT_BY_CLASS_FILENAME)
        return filename if os.path.exists(filename) else DEFAULT_EXPORT_BY_CLASS_SETTINGS_FILE

    async def get_project_publications(self, path: str = Query(..., description="Project directory")):
        try:
            filename = self._publications_filename(path)
            data = load_data(filename)
            publications = []
            for element_class, values in data.items():
                for property_name in values.get("Publish", []):
                    publications.append({"element_class": element_class, "property": property_name, "publish": True})
                for property_name in values.get("NoPublish", []):
                    publications.append({"element_class": element_class, "property": property_name, "publish": False})
            return {"path": filename, "publications": publications}
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def save_project_publications(self, payload: dict = Body(...)):
        try:
            path = payload["path"]
            if not os.path.isdir(path):
                raise FileNotFoundError(path)
            source = self._publications_filename(path)
            data = load_data(source)
            configured = {}
            for item in payload.get("publications", []):
                element_class = item["element_class"]
                property_name = item["property"]
                configured.setdefault(element_class, {"Publish": [], "NoPublish": []})
                key = "Publish" if item.get("publish", False) else "NoPublish"
                configured[element_class][key].append(property_name)
            for element_class, values in configured.items():
                data.setdefault(element_class, {})
                data[element_class]["Publish"] = values["Publish"]
                data[element_class]["NoPublish"] = values["NoPublish"]
            filename = os.path.join(path, "ExportLists", EXPORT_BY_CLASS_FILENAME)
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            dump_data(data, filename)
            return {"saved": True, "path": filename, "publications": payload.get("publications", [])}
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"Missing field: {exc.args[0]}") from exc
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def get_project_monte_carlo(self, path: str = Query(..., description="Project directory")):
        try:
            project, settings = self._load_settings(path)
            configured_samples = settings.monte_carlo.num_scenarios
            variables = []
            sample_outputs = []
            for scenario in project.scenarios:
                filename = os.path.join(
                    project.project_path,
                    "Scenarios",
                    scenario.name,
                    "Monte_Carlo",
                    MONTE_CARLO_SETTINGS_FILENAME,
                )
                if os.path.isfile(filename):
                    for _, values in load_data(filename).items():
                        variables.append({
                            "scenario": scenario.name,
                            "element_class": values.get("Class", ""),
                            "property": values.get("Property", ""),
                            "distribution": values.get("Distribution", ""),
                            "parameters": values.get("Parameters", ""),
                            "wildcard": values.get("Wildcard", ""),
                        })
            store_filename = os.path.join(project.project_path, STORE_FILENAME)
            if os.path.isfile(store_filename):
                with h5py.File(store_filename, "r") as store:
                    sample_outputs = sorted(
                        name for name in store.get("Exports", {}) if "_MC" in name
                    )
            return {
                "configured_samples": configured_samples,
                "variables": variables,
                "sample_outputs": sorted(sample_outputs),
            }
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def get_scenario_controllers(self, scenario_name: str, path: str = Query(...)):
        try:
            project = PyDssProject.load_project(path)
            scenario = project.get_scenario(scenario_name)
            return {
                "scenario": scenario_name,
                "controllers": [
                    {"type": controller_type.value, "settings": settings}
                    for controller_type, settings in scenario.controllers.items()
                ],
            }
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def save_scenario_controllers(self, scenario_name: str, payload: dict = Body(...)):
        try:
            path = payload["path"]
            project = PyDssProject.load_project(path)
            project.get_scenario(scenario_name)
            scenario_dir = os.path.join(path, "Scenarios", scenario_name, "pyControllerList")
            os.makedirs(scenario_dir, exist_ok=True)
            saved = []
            for item in payload.get("controllers", []):
                controller_type = ControllerType(item["type"])
                settings = item.get("settings", {})
                if not isinstance(settings, dict):
                    raise TypeError(f"settings for {controller_type.value} must be an object")
                filename = os.path.join(scenario_dir, filename_from_enum(controller_type))
                dump_data(settings, filename)
                saved.append({"type": controller_type.value, "settings": settings})
            return {"saved": True, "scenario": scenario_name, "controllers": saved}
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"Missing field: {exc.args[0]}") from exc
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def start_simulation(self, request: SimulationStartRequest):
        return self.handler.start_simulation(request.model_dump())

    async def get_project_scenario(
        self,
        scenario_name: str,
        path: str = Query(..., description="Project directory"),
    ):
        try:
            return self.handler.get_project_scenario(path, scenario_name)
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def get_simulation(self, uuid: str):
        try:
            return self.handler.get_simulation_state(uuid)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def get_simulation_events(
        self,
        uuid: str,
        after: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
    ):
        try:
            return self.handler.get_simulation_event_history(uuid, after, limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def submit_simulation_command(self, uuid: str, request: SimulationCommandRequest):
        try:
            return self.handler.submit_command(uuid, request.command, request.parameters)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    async def stop_simulation(self, uuid: str):
        try:
            return self.handler.stop_simulation(uuid)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def create_project(
        self,
        project: str = Form(...),
        scenarios: str = Form(...),
        controller_types: str = Form(""),
        master_file: str = Form("Master.dss"),
        project_path: str | None = Form(None),
        file: UploadFile = File(...),
    ):
        archive = await file.read()
        root = project_path or os.environ.get("PYDSS_PROJECT_ROOT", "./pydss-projects")
        try:
            return self.handler.create_project_from_upload(
                archive=archive,
                project_root=root,
                project=project,
                scenarios=scenarios,
                controller_types=controller_types,
                master_file=master_file,
            )
        except (FileExistsError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
