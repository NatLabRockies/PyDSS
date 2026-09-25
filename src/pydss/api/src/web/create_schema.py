import requests
import json


def get_json_schema(ip, port, path):
    base_url = f"http://{ip}:{port}"
    url = base_url + "/docs/swagger.json"

    response = requests.get(url)
    with open(path, "w") as outfile:
        json.dump(response.json(), outfile)
