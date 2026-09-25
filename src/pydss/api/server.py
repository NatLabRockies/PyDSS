import threading
import requests
import json
import time
import os
import io
import re

from aiohttp_swagger3 import SwaggerDocs, SwaggerUiSettings
from loguru import logger
from aiohttp import web

from pydss.api.src.web.handler import Handler
import pydss.api.schema as schema
import pydss


def read(*names, **kwargs):
    with io.open(
        os.path.join(os.path.dirname(pydss.__file__), *names),
        encoding=kwargs.get("encoding", "utf8"),
    ) as fp:
        return fp.read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


def get_json_schema(host, port):
    base_path = schema.__path__._path[0]
    path = os.path.join(base_path, "pydss.v1.json")
    base_url = f"http://{host}:{port}"
    url = base_url + "/docs/swagger.json"
    is_valid = False
    while not is_valid:
        time.sleep(3)
        response = requests.get(url)
        is_valid = response.status_code == 200
    with open(path, "w") as outfile:
        json.dump(response.json(), outfile, indent=4, sort_keys=True)
    logger.info(f"Export the schema file to {path}")


class PydssServer:
    def __init__(self, host, port):
        self.handler = Handler()
        self.app = web.Application()
        self.swagger = SwaggerDocs(
            self.app,
            title="Pydss RESTful API documentation",
            version=find_version("__init__.py"),
            description="The API enables creating pydss instances, running simulations and creation of new projects.",
            swagger_ui_settings=SwaggerUiSettings(path="/docs/"),
            # components="components.yaml"
        )
        self.register_media_handlers()
        self.add_routes()
        t = threading.Thread(
            name="child procs",
            target=get_json_schema,
            args=(
                host,
                port,
            ),
        )
        t.start()

    def register_media_handlers(self):
        self.swagger.register_media_type_handler(
            "multipart/form-data", self.handler.post_pydss_create
        )
        return

    def add_routes(self):
        self.swagger.add_routes(
            [
                web.get("/simulators/pydss/instances", self.handler.get_instance_uuids),
                web.get("/simulators/pydss/status/uuid/{uuid}", self.handler.get_instance_status),
                web.get("/simulators/pydss/info", self.handler.get_pydss_project_info),
                web.put("/simulators/pydss", self.handler.put_pydss),
                web.post("/simulators/pydss", self.handler.post_pydss),
                web.post(
                    "/simulators/pydss/create", self.handler.post_pydss_create, validate=False
                ),
                web.delete("/simulators/pydss", self.handler.delete_pydss),
            ]
        )

    async def clean_background_tasks(self, app):
        logger.info("cleanup_background_tasks")
        self.handler.event.set()
