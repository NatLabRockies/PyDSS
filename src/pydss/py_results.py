import pandas as pd
import numpy as np
import os


class PyContrReader:
    def __init__(self, path):
        self.pyControllers = {}
        filenames = os.listdir(path)
        for filename in filenames:
            if filename.endswith(".xlsx") and not filename.startswith("~$"):
                controller_type = filename.split(".")[0]
                filepath = os.path.join(path, filename)
                assert os.path.exists(filepath), 'path: "{}" does not exist!'.format(filepath)
                controller_dataset = pd.read_excel(
                    filepath,
                    skiprows=[
                        0,
                    ],
                    index_col=[0],
                )
                controller_names = controller_dataset.index.tolist()
                controllers = {}
                for controller_name in controller_names:
                    controller_data = controller_dataset.loc[controller_name]
                    assert len(controller_data == 1), (
                        "Multiple pydss controller definitions for a single OpenDSS "
                        + "element not allowed"
                    )
                    controller_dict = controller_data.to_dict()
                    controllers[controller_name] = controller_dict
                self.pyControllers[controller_type] = controllers


class PySubscriptionReader:
    def __init__(self, file_path):
        self.SubscriptionDict = {}
        assert os.path.exists(file_path), 'path: "{}" does not exist!'.format(file_path)
        subscription_data = pd.read_excel(
            file_path,
            skiprows=[
                0,
            ],
            index_col=[0],
        )
        required_columns = {"Property", "Subscription ID", "Unit", "Subscribe", "Data type"}
        file_columns = set(subscription_data.columns)
        diff = required_columns.difference(file_columns)

        assert len(diff) == 0, (
            "Missing column in the subscriptions file.\nRequired columns: {}".format(
                required_columns
            )
        )
        subscribe = subscription_data["Subscribe"]
        assert subscribe.dtype == bool, "The subscribe column can only have boolean values."
        self.SubscriptionDict = subscription_data.T.to_dict()


class PyExportReader:
    def __init__(self, file_path):
        self.pyControllers = {}
        self.publicationList = []
        assert os.path.exists(file_path), 'path: "{}" does not exist!'.format(file_path)
        controller_dataset = pd.read_excel(
            file_path,
            skiprows=[
                0,
            ],
            index_col=[0],
        )
        assert controller_dataset.columns[0] == "Publish", (
            "First column after class declarations in the "
            + "export defination files  should have column "
            + 'name "Publish"'
        )

        publish = controller_dataset["Publish"]
        assert publish.dtype == bool, "The publish column can only have boolean values."
        filtered_dataset = controller_dataset[controller_dataset.columns[1:]]

        controller_names = filtered_dataset.index.tolist()
        for controller_name, do_publish in zip(controller_names, publish.values):
            controller_data = filtered_dataset.loc[controller_name]
            publish_data = controller_dataset["Publish"].loc[controller_name]
            if isinstance(publish_data, np.bool_):
                publish_data = [publish_data]
            else:
                publish_data = publish_data.dropna().values
            data = controller_data.copy()
            data.index = range(len(data))
            for i, should_publish in enumerate(publish_data):
                if should_publish:
                    if isinstance(data, pd.core.frame.DataFrame):
                        properties = data.loc[i].dropna()
                    else:
                        properties = data.dropna().values
                    for property_name in properties:
                        self.publicationList.append("{} {}".format(controller_name, property_name))

            if len(controller_data) > 1:
                controller_data = pd.Series(controller_data.values.flatten())
                controller_dict = controller_data.dropna().to_dict()
            else:
                controller_dict = controller_data.dropna().to_dict()

            self.pyControllers[controller_name] = controller_dict
        self.publicationList = list(set(self.publicationList))
