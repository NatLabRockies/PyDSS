from multiprocessing import Queue, Process, Event, cpu_count
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import shutil
import asyncio
import os

from loguru import logger
from aiohttp import web

from pydss.pydss_project import PyDssProject, PyDssScenario, ControllerType
from pydss.api.src.web.parser import bytestream_decode
from pydss.api.src.app.pydss import PyDSS


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
        self.loop = asyncio.get_event_loop()

    async def get_pydss_project_info(self, request, path):
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
            web.json_response(
                {
                    "Status": 404,
                    "Message": "No valid pydss project in provided base path",
                    "UUID": None,
                }
            )

    async def post_pydss_create(self, request):
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

    async def post_pydss_project(self, request):
        return

    async def get_pydss_project(self, request):
        return

    async def post_pydss(self, request):
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

        pydss_uuid = str(uuid4())
        q = Queue()

        # Create a process for pydss instance
        p = Process(target=PyDSS, name=pydss_uuid, args=(self.event, q, data))
        # Store queue and process
        self.pydss_instances[pydss_uuid] = {"queue": q, "process": p}
        # Catching data coming from pydss
        pydss_t = self.loop.run_in_executor(self.pool, self._post_put_background_task, pydss_uuid)
        pydss_t.add_done_callback(self._post_put_callback)

        # Start process for pydss
        p.start()
        # Return a message to webclient
        result = {"Status": 200, "Message": "Starting a pydss instance", "UUID": pydss_uuid}

        return web.json_response(result)

    async def put_pydss(self, request):
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
            pydss_t = self.loop.run_in_executor(
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

    async def delete_pydss(self, request):
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
                pydss_t = self.loop.run_in_executor(
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

    async def get_instance_uuids(self, request):
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

    async def get_instance_status(self, request, uuid: str):
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
        return q.get()

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
