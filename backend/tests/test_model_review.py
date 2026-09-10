import pytest

from backend.app.services.aggregation import aggregate_competencies, confirm_model, update_competency, ImmutableModelError, detect_conflicts
from fastapi.testclient import TestClient
from backend.app.main import app


def test_aggregation_groups_duplicates_and_normalizes_weights() -> None:
    model = aggregate_competencies([
        {"name": "组件化开发", "jd_id": "jd1", "evidence_ids": ["e1"]},
        {"name": "组件化开发", "jd_id": "jd2", "evidence_ids": ["e2"]},
        {"name": "性能优化", "jd_id": "jd1", "evidence_ids": ["e3"]},
    ])
    assert len(model) == 2
    assert sum(item["weight"] for item in model) == pytest.approx(1.0)
    merged = next(item for item in model if item["name"] == "组件化开发")
    assert merged["source_jd_ids"] == ["jd1", "jd2"]
    assert merged["jd_relevance"] == pytest.approx(1.0)
    assert merged["importance_weight"] == pytest.approx(merged["weight"])
    assert merged["source_consistency"] == pytest.approx(1.0)
    assert merged["evidence_ids"] == ["e1", "e2"]

def test_aggregation_respects_user_weights_before_normalizing() -> None:
    model = aggregate_competencies([
        {"name": "组件化开发", "jd_id": "jd1", "evidence_ids": [], "weight": 3},
        {"name": "性能优化", "jd_id": "jd1", "evidence_ids": [], "weight": 1},
    ])
    assert next(item for item in model if item["name"] == "组件化开发")["weight"] == pytest.approx(0.75)


def test_confirmed_model_cannot_be_mutated() -> None:
    model = confirm_model({"status": "DRAFT", "competencies": []})
    with pytest.raises(ImmutableModelError):
        update_competency(model, name="新名称")


def test_detects_similar_names_as_review_conflict() -> None:
    conflicts = detect_conflicts([{"name": "数据分析", "jd_id": "jd1", "evidence_ids": ["e1"]}, {"name": "数据分析能力", "jd_id": "jd2", "evidence_ids": ["e2"]}])
    assert conflicts[0]["type"] == "SIMILAR_NAME"


def test_competency_crud_is_available_for_draft_jd_model() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "能力 CRUD"}).json()
        jd = client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "JD", "text": "负责测试"}).json()
        created = client.post(f"/api/jds/{jd['id']}/competencies", json={"name": "测试设计"})
        assert created.status_code == 201
        competency_id = created.json()["id"]
        assert client.patch(f"/api/competencies/{competency_id}", json={"name": "自动化测试", "weight": 0.7}).status_code == 200
        assert client.delete(f"/api/competencies/{competency_id}").status_code == 204

def test_weight_is_returned_after_model_refresh() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "权重刷新"}).json()
        jd = client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "JD", "text": "负责测试"}).json()
        created = client.post(f"/api/jds/{jd['id']}/competencies", json={"name": "测试设计"}).json()
        client.patch(f"/api/competencies/{created['id']}", json={"weight": 0.6})
        client.post(f"/api/projects/{project['id']}/aggregate")
        latest = client.get(f"/api/projects/{project['id']}/models/latest").json()
        assert latest["competencies"][0]["weight"] == pytest.approx(1.0)
