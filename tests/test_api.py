from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "doppel_artifact_dir", tmp_path)
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_asset_preview(client: TestClient) -> None:
    response = client.get("/api/assets/healthcare")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "healthcare"
    assert payload["row_counts"]["patients"] > 0
    assert payload["previews"]["encounters"]


def test_create_and_download_run(client: TestClient) -> None:
    response = client.post(
        "/api/runs",
        json={"asset_id": "healthcare", "scale": 0.1, "seed": 31, "expiry_days": 30},
    )
    assert response.status_code == 200
    run = response.json()
    download = client.get(f"/api/runs/{run['run_id']}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"


def test_run_stream_endpoint(client: TestClient) -> None:
    with client.stream(
        "POST",
        "/api/runs/stream",
        json={"asset_id": "healthcare", "scale": 1, "seed": 7, "expiry_days": 7},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                events.append(line[6:])
        complete = events[-1]
        assert '"type": "complete"' in complete
        assert '"decision": "VERIFIED"' in complete
