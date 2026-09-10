"""Runnable three-stage demo flow; uses deterministic no-key AI fallback."""

from fastapi.testclient import TestClient

from backend.app.main import app


def test_three_stage_flow_prints_results(monkeypatch, capsys) -> None:
    monkeypatch.setattr("backend.app.services.assessment_ai.get_llm_api_key", lambda: None)
    with TestClient(app) as client:
        # Stage 1: JD -> parsed model -> confirmed snapshot.
        project = client.post("/api/projects", json={"name": "三阶段演示岗位"}).json()
        client.post(f"/api/projects/{project['id']}/jds/text", json={"title": "产品工程师", "text": "负责 React 组件开发，优化页面性能，并与团队沟通协作。"})
        client.post(f"/api/projects/{project['id']}/analysis/run")
        model = client.post(f"/api/projects/{project['id']}/aggregate").json()
        confirmed = client.post(f"/api/models/{model['id']}/confirm")
        assert confirmed.status_code == 201
        print(f"阶段一｜模型：{confirmed.json()['status']}｜能力项：{len(confirmed.json()['competencies'])}")

        # Stage 2: create/start/finish a partial text assessment.
        session = client.post(f"/api/projects/{project['id']}/assessments", json={"model_version_id": model["id"]}).json()
        started = client.post(f"/api/assessments/{session['id']}/start").json()
        assert started["status"] == "IN_PROGRESS"
        finished = client.post(f"/api/assessments/{session['id']}/finish", json={"confirm": True, "reason": "演示完成"})
        assert finished.status_code == 200
        package = client.get(f"/api/assessments/{session['id']}/evidence-package")
        assert package.status_code == 200
        print(f"阶段二｜证据包：{package.json()['completion']}｜能力项：{len(package.json()['competencies'])}")

        # Stage 3: create/activate rubric, then generate a versioned report.
        competencies = [{"id": item["competency_id"], "name": item["name"], "weight": 1.0} for item in session["competencies"]]
        rubric = client.post(f"/api/model-versions/{model['id']}/rubrics", json={"version": "demo-r1", "competencies": competencies}).json()
        assert client.post(f"/api/rubric-sets/{rubric['id']}/activate").status_code == 200
        report = client.post(f"/api/assessment-sessions/{session['id']}/reports", json={"evidence_package_id": session["id"], "rubric_set_id": rubric["id"], "idempotency_key": "demo-report-1", "evidence_package": package.json()})
        assert report.status_code == 200
        body = report.json()
        print(f"阶段三｜报告：v{body['report_version']}｜匹配度：{body['match_score'] if body['match_score'] is not None else '待评价'}｜叙述：{body['narrative_status']}")

    output = capsys.readouterr().out
    print(output, end="")
    assert "阶段一｜模型：CONFIRMED" in output
    assert "阶段二｜证据包：PARTIAL" in output
    assert "阶段三｜报告：v1" in output
