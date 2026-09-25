import json
import os


class JsonWriter:
    def __init__(self, log_dir, column_length=None):
        self.log_dir = log_dir
        self.metadata = False
        self.payload = False
        return

    def parse_metadata(self, class_name, load_flow_results, results):
        for key, value in load_flow_results[class_name].items():
            data = key.split("__")
            name = data[0]
            if len(data) == 3:
                ppty = f"{data[1]}__{data[2]}"
            else:
                ppty = data[1]
            asset = self.check_asset(class_name, None, results)
            if not asset:
                asset = {
                    "assetType": class_name,
                    "keyColumns": "Name",
                    "keyValues": [name],
                    "measurementColumns": [
                        {
                            "name": ppty,
                            "type": "numeric" if not isinstance(value, str) else "string",
                            "mappings": {},
                        }
                    ],
                }
                results["assets"].append(asset)
            else:
                if name not in asset["keyValues"]:
                    asset["keyValues"].append(name)
                column_exists = False
                for column in asset["measurementColumns"]:
                    if column["name"] == ppty:
                        column_exists = True
                if not column_exists:
                    res = {
                        "name": ppty,
                        "type": "numeric" if not isinstance(value, str) else "string",
                        "mappings": {},
                    }
                    asset["measurementColumns"].append(res)
        return results

    def create_meta_data(
        self, load_flow_results, fed_name, fed_uuid, cosim_uuid, circuit, current_time
    ):
        results = {}
        results["cosimUUID"] = cosim_uuid
        results["federateUUID"] = fed_uuid
        results["interconnect"] = "distribution"
        results["assets"] = []
        for key in load_flow_results:
            results = self.parse_metadata(key, load_flow_results, results)
        return results

    def update_payload(self, timestep, fed_uuid, cosim_uuid):
        if not self.payload:
            self.payload = {
                "cosimUUID": cosim_uuid,
                "federateUUID": fed_uuid,
                "timeSteps": [timestep],
            }
        else:
            self.payload["timeSteps"].append(timestep)
        return

    def write(
        self,
        fed_name,
        current_time,
        load_flow_results,
        index=None,
        circuit=None,
        fed_uuid=None,
        cosim_uuid=None,
    ):
        json_file = open(os.path.join(self.log_dir, f"Results_{int(current_time)}.json"), "w")
        payload_file = open(os.path.join(self.log_dir, "payload.json"), "w")
        if not self.metadata:
            metadata_file = open(os.path.join(self.log_dir, "metadata.json"), "w")
            self.metadata = self.create_meta_data(
                load_flow_results, fed_name, fed_uuid, cosim_uuid, circuit, current_time
            )
            json.dump(self.metadata, metadata_file, indent=4, sort_keys=True)
            metadata_file.close()
        results = self.remap(
            load_flow_results, fed_name, fed_uuid, cosim_uuid, circuit, current_time
        )
        self.update_payload(current_time, fed_uuid, cosim_uuid)
        json.dump(results, json_file, indent=4, sort_keys=True)
        json.dump(self.payload, payload_file, indent=4, sort_keys=True)
        json_file.close()
        payload_file.close()
        return

    def __del__(self):
        return

    def check_asset(self, class_name, property_name, results):
        for asset in results["assets"]:
            if property_name is not None:
                if (
                    "assetType" in asset
                    and asset["assetType"] == class_name
                    and property_name in asset
                ):
                    return asset
            else:
                if "assetType" in asset and asset["assetType"] == class_name:
                    return asset
        return False

    def parse_class(self, class_name, load_flow_results, results):
        for key, value in load_flow_results[class_name].items():
            data = key.split("__")
            if len(data) == 3:
                ppty = f"{data[1]}__{data[2]}"
            else:
                ppty = data[1]
            asset = self.check_asset(class_name, ppty, results)
            if not asset:
                asset = {"assetType": class_name, ppty: [value]}
                results["assets"].append(asset)
            else:
                asset[ppty].append(value)
        return results

    def remap(self, load_flow_results, fed_name, fed_uuid, cosim_uuid, circuit, current_time):
        results = {}
        results["cosimUUID"] = cosim_uuid
        results["federateUUID"] = fed_uuid
        results["timeStep"] = current_time
        results["assets"] = []
        for key in load_flow_results:
            results = self.parse_class(key, load_flow_results, results)
        return results


globals()["JSONwriter"] = JsonWriter
