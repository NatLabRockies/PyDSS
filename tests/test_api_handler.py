import io
from zipfile import ZipFile

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
import pytest

from pydss.api.server import PydssServer
from pydss.api.src.web.handler import Handler


class Scenario:
    name = "base_case"

    def get_dataframe(self, element_class, prop, element_name, **kwargs):
        assert (element_class, prop, element_name) == ("Buses", "puVmagAngle", "sourcebus")
        return pd.DataFrame(
            {"sourcebus__pu": np.array([1.0, 1.01, 0.99])},
            index=pd.to_datetime(
                ["2026-01-01", "2026-01-01 00:15", "2026-01-01 00:30"], format="mixed"
            ),
        )


class Results:
    def get_scenario(self, name):
        assert name == "base_case"
        return Scenario()


def test_result_timeseries_is_paginated_and_json_serializable(monkeypatch):
    monkeypatch.setattr(Handler, "_load_results", staticmethod(lambda path: Results()))
    app = PydssServer("127.0.0.1", 8000).app
    client = TestClient(app)
    response = client.get(
        "/api/v1/results/timeseries",
        params={
            "path": "/tmp/project",
            "scenario": "base_case",
            "element_class": "Buses",
            "property": "puVmagAngle",
            "element_name": "sourcebus",
            "offset": "1",
            "limit": "1",
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["total"] == 3
    assert payload["offset"] == 1
    assert len(payload["rows"]) == 1
    assert payload["rows"][0]["timestamp"] == "2026-01-01T00:15:00"
    assert payload["rows"][0]["values"]["sourcebus__pu"] == 1.01


def test_result_timeseries_rejects_missing_query_parameters():
    client = TestClient(PydssServer("127.0.0.1", 8000).app)
    response = client.get("/api/v1/results/timeseries", params={"path": "/tmp/project"})
    payload = response.json()

    assert response.status_code == 400
    assert "Missing query parameters" in payload["error"]["message"]


def test_project_upload_accepts_multipart_form(monkeypatch, tmp_path):
    monkeypatch.setattr(
        Handler,
        "create_project_from_upload",
        lambda self, **kwargs: {"Status": 200, "project_path": str(tmp_path / "demo")},
    )
    archive = io.BytesIO()
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("Master.dss", "clear")

    client = TestClient(PydssServer("127.0.0.1", 8000).app)
    response = client.post(
        "/simulators/pydss/create",
        data={
            "project": "demo",
            "scenarios": "base_case",
            "controller_types": "",
            "master_file": "Master.dss",
            "project_path": str(tmp_path),
        },
        files={"file": ("project.zip", archive.getvalue(), "application/zip")},
    )

    assert response.status_code == 200
    assert response.json()["Status"] == 200


def test_project_upload_rejects_unsafe_zip_path(tmp_path):
    archive = io.BytesIO()
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("../outside.txt", "unsafe")

    with pytest.raises(ValueError, match="unsafe path"):
        Handler().create_project_from_upload(
            archive=archive.getvalue(),
            project_root=str(tmp_path),
            project="demo",
            scenarios="base_case",
            controller_types="",
            master_file="Master.dss",
        )


def test_api_allows_vue_development_origin():
    client = TestClient(PydssServer("127.0.0.1", 8000).app)
    response = client.options(
        "/api/v1/simulations",
        headers={
            "Origin": "http://localhost:8080",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8080"


def test_missing_simulation_returns_json_404():
    client = TestClient(PydssServer("127.0.0.1", 8000).app)
    response = client.get("/api/v1/simulations/missing")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]
