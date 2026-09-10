import pytest
from fastapi.testclient import TestClient

from backend.app.db import SessionLocal
from backend.app.main import app
from backend.app.services.assessment_contracts import (
    ModelNotConfirmedError,
    get_confirmed_model_snapshot,
)


def _create_model(client: TestClient) -> tuple[dict, dict]:
    project = client.post("/api/projects", json={"name": "阶段交接"}).json()
    client.post(
        f"/api/projects/{project['id']}/jds/text",
        json={"title": "前端工程师", "text": "负责 React 组件开发，优化页面性能"},
    )
    client.post(f"/api/projects/{project['id']}/analysis/run")
    model = client.post(f"/api/projects/{project['id']}/aggregate").json()
    return project, model


def test_snapshot_rejects_draft_model() -> None:
    with TestClient(app) as client:
        project, model = _create_model(client)
        with SessionLocal() as db, pytest.raises(ModelNotConfirmedError):
            get_confirmed_model_snapshot(db, project["id"], model["id"])


def test_snapshot_preserves_confirmed_version_order_weights_and_evidence() -> None:
    with TestClient(app) as client:
        project, model = _create_model(client)
        client.post(f"/api/models/{model['id']}/confirm")

        with SessionLocal() as db:
            snapshot = get_confirmed_model_snapshot(db, project["id"])

        assert snapshot.model_version_id == model["id"]
        assert snapshot.version == "v1.0"
        assert [item.name for item in snapshot.competencies] == [
            item["name"] for item in model["competencies"]
        ]
        assert sum(item.weight for item in snapshot.competencies) == pytest.approx(1.0)
        assert all(item.jd_evidence_ids for item in snapshot.competencies)
