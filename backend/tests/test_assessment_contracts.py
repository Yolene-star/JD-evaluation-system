import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.db import SessionLocal
from backend.app.main import app
from backend.app.models import ModelSnapshot
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
        assert all(item.indicators == () for item in snapshot.competencies)
        assert all(item.evidence_requirements == () for item in snapshot.competencies)


def test_snapshot_preserves_optional_indicators_and_evidence_requirements() -> None:
    """Would fail if new formal fields are discarded while loading old-compatible snapshots."""
    with TestClient(app) as client:
        project, model = _create_model(client)
        client.post(f"/api/models/{model['id']}/confirm")

        with SessionLocal() as db:
            stored = db.scalar(
                select(ModelSnapshot).where(ModelSnapshot.model_version_id == model["id"])
            )
            assert stored is not None
            stored.snapshot_json = {
                **stored.snapshot_json,
                "competencies": [
                    {
                        **stored.snapshot_json["competencies"][0],
                        "indicators": ["说明技术选型依据"],
                        "evidence_requirements": ["本人行动", "可验证结果"],
                    },
                    *stored.snapshot_json["competencies"][1:],
                ],
            }
            db.commit()
            confirmed = get_confirmed_model_snapshot(db, project["id"])

        assert confirmed.competencies[0].indicators == ("说明技术选型依据",)
        assert confirmed.competencies[0].evidence_requirements == ("本人行动", "可验证结果")
