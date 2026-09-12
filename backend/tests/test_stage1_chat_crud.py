from fastapi.testclient import TestClient

from backend.app.main import app


def _project_with_analyzed_jd(client: TestClient) -> tuple[dict, dict]:
    project = client.post("/api/projects", json={"name": "对话 CRUD"}).json()
    jd = client.post(
        f"/api/projects/{project['id']}/jds/text",
        json={
            "title": "前端工程师 JD",
            "text": "岗位职责：负责 React 组件开发和页面性能优化。任职要求：熟悉 TypeScript。",
        },
    ).json()
    response = client.post(f"/api/projects/{project['id']}/analysis/run")
    assert response.status_code == 200
    return project, jd


def test_chat_renames_a_jd_and_records_a_system_notice() -> None:
    with TestClient(app) as client:
        project, jd = _project_with_analyzed_jd(client)

        response = client.post(
            f"/api/projects/{project['id']}/chat",
            json={"message": "把前端工程师 JD 改名为高级前端工程师 JD"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["operation"]["action"] == "RENAME_JD"
        assert body["operation"]["requires_confirmation"] is False
        assert "高级前端工程师 JD" in body["system_notices"][0]
        assert client.get(f"/api/projects/{project['id']}/analysis").json()["jds"][0]["title"] == "高级前端工程师 JD"
        events = client.get(f"/api/projects/{project['id']}/events").json()
        assert events[0]["action"] == "JD_UPDATED"
        assert jd["id"] in events[0]["payload"]


def test_chat_creates_a_single_jd_competency() -> None:
    with TestClient(app) as client:
        project, _ = _project_with_analyzed_jd(client)

        response = client.post(
            f"/api/projects/{project['id']}/chat",
            json={"message": "在前端工程师 JD 中新增跨团队沟通能力"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["operation"]["action"] == "CREATE_COMPETENCY"
        assert body["operation"]["requires_confirmation"] is False
        names = [item["name"] for item in client.get(f"/api/projects/{project['id']}/analysis").json()["jds"][0]["competencies"]]
        assert "跨团队沟通" in names


def test_chat_weight_update_requires_confirmation_then_saves_and_normalizes() -> None:
    with TestClient(app) as client:
        project, _ = _project_with_analyzed_jd(client)
        message = "把前端工程师 JD 中组件化开发的权重改成 25%"

        preview = client.post(f"/api/projects/{project['id']}/chat", json={"message": message})
        assert preview.status_code == 200
        assert preview.json()["operation"] == {
            "action": "UPDATE_COMPETENCY_WEIGHT",
            "requires_confirmation": True,
            "scope": "single",
            "target": "组件化开发",
            "value": 0.25,
        }

        done = client.post(
            f"/api/projects/{project['id']}/chat",
            json={"message": message, "confirm": True},
        )
        assert done.status_code == 200
        assert done.json()["operation"]["action"] == "UPDATE_COMPETENCY_WEIGHT"
        competencies = client.get(f"/api/projects/{project['id']}/analysis").json()["jds"][0]["competencies"]
        weights = {item["name"]: item["weight"] for item in competencies}
        assert abs(sum(weights.values()) - 1.0) < 1e-9
        assert abs(weights["组件化开发"] - 0.25) < 1e-9


def test_chat_delete_competency_requires_confirmation_then_deletes() -> None:
    with TestClient(app) as client:
        project, _ = _project_with_analyzed_jd(client)
        message = "删除前端工程师 JD 中的性能优化能力"

        preview = client.post(f"/api/projects/{project['id']}/chat", json={"message": message}).json()
        assert preview["operation"]["action"] == "DELETE_COMPETENCY"
        assert preview["operation"]["requires_confirmation"] is True

        done = client.post(
            f"/api/projects/{project['id']}/chat",
            json={"message": message, "confirm": True},
        )
        assert done.status_code == 200
        names = [item["name"] for item in client.get(f"/api/projects/{project['id']}/analysis").json()["jds"][0]["competencies"]]
        assert "性能优化" not in names


def test_chat_queries_real_competency_evidence() -> None:
    with TestClient(app) as client:
        project, _ = _project_with_analyzed_jd(client)

        response = client.post(
            f"/api/projects/{project['id']}/chat",
            json={"message": "查看组件化开发的证据"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["operation"]["action"] == "QUERY_EVIDENCE"
        assert "React" in body["reply"]
        assert body["operation"]["result"]["evidence"]


def test_chat_renames_a_competency_and_lists_the_updated_model() -> None:
    with TestClient(app) as client:
        project, _ = _project_with_analyzed_jd(client)

        renamed = client.post(
            f"/api/projects/{project['id']}/chat",
            json={"message": "把前端工程师 JD 中的组件化开发能力改名为组件工程"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["operation"]["action"] == "UPDATE_COMPETENCY_NAME"

        listed = client.post(
            f"/api/projects/{project['id']}/chat",
            json={"message": "查看前端工程师 JD 有哪些能力"},
        )
        assert listed.status_code == 200
        assert listed.json()["operation"]["action"] == "LIST_COMPETENCIES"
        assert "组件工程" in listed.json()["reply"]
        assert "组件化开发" not in listed.json()["reply"]


def test_chat_readds_a_removed_jd() -> None:
    with TestClient(app) as client:
        project, jd = _project_with_analyzed_jd(client)
        client.patch(f"/api/jds/{jd['id']}", json={"participates_in_model": False})

        response = client.post(
            f"/api/projects/{project['id']}/chat",
            json={"message": "把前端工程师 JD 重新加入模型"},
        )

        assert response.status_code == 200
        assert response.json()["operation"]["action"] == "READD_JD"
        assert client.get(f"/api/projects/{project['id']}/analysis").json()["jds"][0]["participates_in_model"] is True


def test_chat_creates_and_weights_a_total_model_competency() -> None:
    with TestClient(app) as client:
        project, _ = _project_with_analyzed_jd(client)
        generated = client.post(f"/api/projects/{project['id']}/chat", json={"message": "生成总模型"}).json()
        model_id = generated["operation"]["result"]["model_id"]
        single_before = client.get(f"/api/projects/{project['id']}/analysis").json()["jds"][0]["competencies"]
        single_weights_before = {item["name"]: item["weight"] for item in single_before}

        created = client.post(
            f"/api/projects/{project['id']}/chat",
            json={"message": "在总模型中新增用户研究能力"},
        )
        assert created.status_code == 200
        assert created.json()["operation"]["action"] == "CREATE_COMPETENCY"
        assert created.json()["operation"]["result"]["scope"] == "total"

        message = "把总模型中用户研究的权重改成 20%"
        preview = client.post(f"/api/projects/{project['id']}/chat", json={"message": message}).json()
        assert preview["operation"]["scope"] == "total"
        saved = client.post(
            f"/api/projects/{project['id']}/chat",
            json={"message": message, "confirm": True},
        )
        assert saved.status_code == 200
        total_model = client.get(f"/api/models/{model_id}").json()
        weights = {item["name"]: item["weight"] for item in total_model["competencies"]}
        assert abs(weights["用户研究"] - 0.2) < 1e-9
        assert abs(sum(weights.values()) - 1.0) < 1e-9
        single_after = client.get(f"/api/projects/{project['id']}/analysis").json()["jds"][0]["competencies"]
        assert {item["name"]: item["weight"] for item in single_after} == single_weights_before
        assert "用户研究" not in {item["name"] for item in single_after}


def test_chat_generates_total_model_and_requires_confirmation_to_freeze() -> None:
    with TestClient(app) as client:
        project, _ = _project_with_analyzed_jd(client)

        generated = client.post(
            f"/api/projects/{project['id']}/chat",
            json={"message": "生成总模型"},
        )
        assert generated.status_code == 200
        model_id = generated.json()["operation"]["result"]["model_id"]

        preview = client.post(
            f"/api/projects/{project['id']}/chat",
            json={"message": "确认并冻结模型"},
        ).json()
        assert preview["operation"]["action"] == "CONFIRM_MODEL"
        assert preview["operation"]["requires_confirmation"] is True

        confirmed = client.post(
            f"/api/projects/{project['id']}/chat",
            json={"message": "确认并冻结模型", "confirm": True},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["operation"]["result"]["model_id"] == model_id
        assert client.get(f"/api/models/{model_id}").json()["status"] == "CONFIRMED"
