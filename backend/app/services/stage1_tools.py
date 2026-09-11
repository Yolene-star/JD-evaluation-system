from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Competency, Evidence, JobDescription, ModelSnapshot, ModelVersion, ModelVersionStatus, Project
from .aggregation import aggregate_competencies, detect_conflicts
from .analysis import analyze_project_jds
from .audit import record_event
from .stage1_intent import Stage1Intent
from .weights import apply_exact_mapping_weight, apply_exact_weight


CONFIRMATION_TOOLS = {"DELETE_PROJECT", "REMOVE_JD", "DELETE_COMPETENCY", "UPDATE_COMPETENCY_WEIGHT", "CONFIRM_MODEL"}


def _editable(db: Session, project_id: str) -> None:
    frozen = db.scalar(
        select(ModelSnapshot)
        .join(ModelVersion, ModelSnapshot.model_version_id == ModelVersion.id)
        .where(ModelVersion.project_id == project_id)
    )
    if frozen:
        raise HTTPException(status_code=409, detail="已确认模型不可修改，请创建新版本")


def _jd(db: Session, project_id: str, title: str | None) -> JobDescription:
    rows = db.scalars(select(JobDescription).where(JobDescription.project_id == project_id)).all()
    matches = [row for row in rows if row.title == title]
    if not matches:
        raise HTTPException(status_code=404, detail=f"未找到 JD《{title or ''}》")
    if len(matches) > 1:
        raise HTTPException(status_code=409, detail=f"存在多份同名 JD《{title}》，请先修改名称后再操作")
    return matches[0]


def _competencies(db: Session, project_id: str, name: str, jd_title: str | None = None) -> list[Competency]:
    query = select(Competency).join(JobDescription, Competency.jd_id == JobDescription.id).where(
        JobDescription.project_id == project_id,
        Competency.name == name,
    )
    if jd_title:
        query = query.where(JobDescription.title == jd_title)
    rows = db.scalars(query).all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"未找到能力“{name}”")
    return rows


def _aggregate(db: Session, project_id: str) -> tuple[ModelVersion, list[dict], list[dict]]:
    jds = db.scalars(select(JobDescription).where(JobDescription.project_id == project_id, JobDescription.participates_in_model.is_(True))).all()
    items = [
        {"name": row.name, "jd_id": jd.id, "evidence_ids": row.evidence_ids, "weight": row.weight}
        for jd in jds
        for row in db.scalars(select(Competency).where(Competency.jd_id == jd.id)).all()
    ]
    competencies = aggregate_competencies(items)
    conflicts = detect_conflicts(items)
    model = ModelVersion(project_id=project_id, version="draft", status=ModelVersionStatus.DRAFT, draft_json={"competencies": competencies, "conflicts": conflicts, "manual_overrides": False})
    db.add(model)
    db.flush()
    return model, competencies, conflicts


def _latest_draft(db: Session, project_id: str) -> ModelVersion:
    model = db.scalar(
        select(ModelVersion)
        .where(ModelVersion.project_id == project_id, ModelVersion.status == ModelVersionStatus.DRAFT)
        .order_by(ModelVersion.created_at.desc())
    )
    if not model:
        model, _, _ = _aggregate(db, project_id)
    return model


def preview_for(intent: Stage1Intent) -> dict | None:
    if intent.tool not in CONFIRMATION_TOOLS:
        return None
    args = intent.arguments
    operation = {"action": intent.tool, "requires_confirmation": True}
    if intent.tool == "UPDATE_COMPETENCY_WEIGHT":
        operation.update({"scope": args.get("scope", "total"), "target": args.get("competency_name"), "value": args.get("value")})
    elif args.get("competency_name"):
        operation["target"] = args["competency_name"]
    elif args.get("jd_title"):
        operation["target"] = args["jd_title"]
    messages = {
        "DELETE_PROJECT": "该操作会归档整个项目及其测评历史，归档后不会再显示在任务列表中。",
        "REMOVE_JD": "移出后该 JD 不再参与总模型，但原文、解析结果和证据仍会保留。",
        "DELETE_COMPETENCY": "删除后能力项会从模型草稿移除，原始 JD 和证据仍会保留。",
        "UPDATE_COMPETENCY_WEIGHT": "保存后系统会自动重新归一化同一模型中的其他能力权重。",
        "CONFIRM_MODEL": "确认后将生成不可变的 v1.0 快照，当前草稿不能再原地修改。",
    }
    return {"reply": messages[intent.tool] + "请确认是否执行。", "operation": operation}


def execute_stage1_tool(db: Session, project: Project, intent: Stage1Intent) -> dict:
    tool, args = intent.tool, intent.arguments
    if tool in CONFIRMATION_TOOLS or tool in {"RENAME_JD", "READD_JD", "ANALYZE_JD", "CREATE_COMPETENCY", "UPDATE_COMPETENCY_NAME"}:
        _editable(db, project.id)
    notice = ""
    result: dict = {}

    if tool == "DELETE_PROJECT":
        project.status = "ARCHIVED"
        record_event(db, project.id, "PROJECT_ARCHIVED", {"source": "conversation"})
        notice = f"已归档项目《{project.name}》，它不会再出现在任务列表中。"
        reply = notice
        result = {"project_id": project.id, "status": project.status}
    elif tool == "LIST_JDS":
        rows = db.scalars(select(JobDescription).where(JobDescription.project_id == project.id)).all()
        result = {"jds": [{"id": row.id, "title": row.title, "status": row.status.value, "participates_in_model": row.participates_in_model} for row in rows]}
        reply = "当前任务的 JD：\n" + ("\n".join(f"- {row.title}（{row.status.value}，{'参与模型' if row.participates_in_model else '已移出'}）" for row in rows) or "- 暂无 JD")
    elif tool == "RENAME_JD":
        row = _jd(db, project.id, args.get("jd_title")); old = row.title
        new_title = str(args.get("new_title", "")).strip()
        if not new_title: raise HTTPException(status_code=422, detail="JD 标题不能为空")
        row.title = new_title
        record_event(db, project.id, "JD_UPDATED", {"jd_id": row.id, "before": old, "title": new_title, "source": "conversation"})
        notice = f"岗位名称已从“{old}”更新为“{new_title}”。"; reply = notice; result = {"jd_id": row.id, "title": new_title}
    elif tool == "REMOVE_JD":
        row = _jd(db, project.id, args.get("jd_title")); row.participates_in_model = False
        record_event(db, project.id, "JD_REMOVED", {"jd_id": row.id, "title": row.title, "source": "conversation"})
        notice = f"已将《{row.title}》移出总模型，原文和证据仍保留。"; reply = notice; result = {"jd_id": row.id}
    elif tool == "READD_JD":
        row = _jd(db, project.id, args.get("jd_title")); row.participates_in_model = True
        record_event(db, project.id, "JD_READD", {"jd_id": row.id, "title": row.title, "source": "conversation"})
        notice = f"已将《{row.title}》重新加入当前模型。"; reply = notice; result = {"jd_id": row.id}
    elif tool == "ANALYZE_JD":
        title = args.get("jd_title"); row = _jd(db, project.id, title) if title else None
        ids = analyze_project_jds(db, project, jd_ids={row.id} if row else None)
        notice = f"已完成{'《' + row.title + '》' if row else '全部 JD'}的重新解析，单份 JD 模型已刷新。"; reply = notice; result = {"jd_ids": ids}
    elif tool == "LIST_COMPETENCIES":
        title = args.get("jd_title")
        if args.get("scope") == "total" and not title:
            model = _latest_draft(db, project.id)
            items = list((model.draft_json or {}).get("competencies", []))
            result = {"competencies": items, "model_id": model.id}
            reply = "当前总模型能力项：\n" + ("\n".join(f"- {row['name']}（{round(float(row.get('weight', 0)) * 100)}%）" for row in items) or "- 暂无能力项")
        else:
            query = select(Competency).join(JobDescription).where(JobDescription.project_id == project.id)
            if title: query = query.where(JobDescription.title == title)
            rows = db.scalars(query).all()
            result = {"competencies": [{"id": row.id, "name": row.name, "weight": row.weight, "jd_id": row.jd_id} for row in rows]}
            reply = "当前能力项：\n" + ("\n".join(f"- {row.name}（{round(row.weight * 100)}%）" for row in rows) or "- 暂无能力项")
    elif tool == "CREATE_COMPETENCY":
        name = str(args.get("name", "")).strip()
        if not name: raise HTTPException(status_code=422, detail="能力名称不能为空")
        if args.get("scope") == "total":
            model = _latest_draft(db, project.id)
            draft = dict(model.draft_json or {})
            items = [dict(item) for item in draft.get("competencies", [])]
            if any(item.get("name") == name for item in items):
                raise HTTPException(status_code=409, detail=f"总模型已存在能力“{name}”")
            row = {"name": name, "source_jd_ids": [], "evidence_ids": [], "weight": 0.0, "user_supplied": True}
            items.append(row)
            apply_exact_mapping_weight(items, row, 1 / len(items))
            draft["competencies"] = items; draft["manual_overrides"] = True; model.draft_json = draft
            record_event(db, project.id, "COMPETENCY_CREATED", {"model_id": model.id, "name": name, "scope": "total", "source": "conversation"})
            notice = f"已在总模型中新增用户补充能力“{name}”，当前尚未关联 JD 原文证据。"; reply = notice; result = {"model_id": model.id, "name": name, "scope": "total"}
        else:
            jd = _jd(db, project.id, args.get("jd_title"))
            row = Competency(jd_id=jd.id, name=name, evidence_ids=[])
            db.add(row); db.flush()
            siblings = db.scalars(select(Competency).where(Competency.jd_id == jd.id)).all()
            for sibling in siblings: sibling.weight = 1 / len(siblings)
            record_event(db, project.id, "COMPETENCY_CREATED", {"competency_id": row.id, "jd_id": jd.id, "name": name, "source": "conversation"})
            notice = f"已在《{jd.title}》中新增用户补充能力“{name}”，当前尚未关联 JD 原文证据。"; reply = notice; result = {"competency_id": row.id, "jd_id": jd.id, "name": name, "scope": "single"}
    elif tool in {"UPDATE_COMPETENCY_NAME", "DELETE_COMPETENCY"}:
        if args.get("scope") == "total" and not args.get("jd_title"):
            model = _latest_draft(db, project.id); draft = dict(model.draft_json or {}); items = [dict(item) for item in draft.get("competencies", [])]
            matches = [item for item in items if item.get("name") == args.get("competency_name")]
            if not matches: raise HTTPException(status_code=404, detail=f"未找到总模型能力“{args.get('competency_name')}”")
            if tool == "UPDATE_COMPETENCY_NAME":
                new_name = str(args.get("new_name", "")).strip()
                if not new_name: raise HTTPException(status_code=422, detail="能力名称不能为空")
                matches[0]["name"] = new_name; notice = f"总模型能力已更新为“{new_name}”。"; result = {"model_id": model.id, "name": new_name}
            else:
                items.remove(matches[0])
                total = sum(float(item.get("weight") or 0) for item in items)
                if total:
                    for item in items: item["weight"] = float(item.get("weight") or 0) / total
                notice = f"已从总模型草稿删除能力“{args.get('competency_name')}”。"; result = {"model_id": model.id}
            draft["competencies"] = items; draft["manual_overrides"] = True; model.draft_json = draft; reply = notice
            record_event(db, project.id, "COMPETENCY_UPDATED" if tool == "UPDATE_COMPETENCY_NAME" else "COMPETENCY_DELETED", {"model_id": model.id, "name": args.get("competency_name"), "scope": "total", "source": "conversation"})
        else:
            rows = _competencies(db, project.id, args.get("competency_name"), args.get("jd_title"))
            if tool == "UPDATE_COMPETENCY_NAME":
                new_name = str(args.get("new_name", "")).strip()
                if not new_name: raise HTTPException(status_code=422, detail="能力名称不能为空")
                for row in rows: row.name = new_name
                record_event(db, project.id, "COMPETENCY_UPDATED", {"competency_ids": [row.id for row in rows], "name": new_name, "source": "conversation"})
                notice = f"能力已更新为“{new_name}”。"; reply = notice; result = {"competency_ids": [row.id for row in rows], "name": new_name}
            else:
                ids = [row.id for row in rows]
                for row in rows: db.delete(row)
                record_event(db, project.id, "COMPETENCY_DELETED", {"competency_ids": ids, "name": args.get("competency_name"), "source": "conversation"})
                notice = f"已删除能力“{args.get('competency_name')}”，原始 JD 和证据仍保留。"; reply = notice; result = {"competency_ids": ids}
    elif tool == "UPDATE_COMPETENCY_WEIGHT":
        value = float(args.get("value"))
        if args.get("scope") == "total" and not args.get("jd_title"):
            model = _latest_draft(db, project.id); draft = dict(model.draft_json or {}); items = [dict(item) for item in draft.get("competencies", [])]
            matches = [item for item in items if item.get("name") == args.get("competency_name")]
            if not matches: raise HTTPException(status_code=404, detail=f"未找到总模型能力“{args.get('competency_name')}”")
            try: apply_exact_mapping_weight(items, matches[0], value)
            except ValueError as exc: raise HTTPException(status_code=422, detail="权重必须在 0% 到 100% 之间") from exc
            draft["competencies"] = items; draft["manual_overrides"] = True; model.draft_json = draft
            result = {"model_id": model.id, "weight": value, "scope": "total"}
        else:
            matches = _competencies(db, project.id, args.get("competency_name"), args.get("jd_title")); affected_jds: list[str] = []
            for target in matches:
                siblings = db.scalars(select(Competency).where(Competency.jd_id == target.jd_id)).all()
                try: apply_exact_weight(siblings, target, value)
                except ValueError as exc: raise HTTPException(status_code=422, detail="权重必须在 0% 到 100% 之间") from exc
                affected_jds.append(target.jd_id)
            result = {"competency_ids": [row.id for row in matches], "weight": value, "affected_jd_ids": affected_jds, "scope": "single"}
        record_event(db, project.id, "COMPETENCY_WEIGHT_UPDATED", {"name": args.get("competency_name"), "weight": value, "scope": args.get("scope"), "source": "conversation"})
        notice = f"能力“{args.get('competency_name')}”的权重已更新为 {value * 100:g}%，相关权重已自动归一化。"; reply = notice
    elif tool == "QUERY_EVIDENCE":
        rows = _competencies(db, project.id, args.get("competency_name"), args.get("jd_title"))
        evidence_ids = [item for row in rows for item in (row.evidence_ids or [])]
        evidence = db.scalars(select(Evidence).where(Evidence.id.in_(evidence_ids))).all() if evidence_ids else []
        result = {"evidence": [{"id": row.id, "excerpt": row.excerpt, "jd_id": row.jd_id, "start_offset": row.start_offset, "end_offset": row.end_offset} for row in evidence]}
        reply = f"能力“{args.get('competency_name')}”的证据：\n" + ("\n".join(f"- [{row.id}] {row.excerpt}" for row in evidence) or "- 该能力由用户补充，当前尚未关联可回溯的 JD 原文证据。")
    elif tool == "GENERATE_TOTAL_MODEL":
        model, competencies, conflicts = _aggregate(db, project.id)
        record_event(db, project.id, "MODEL_AGGREGATED", {"model_id": model.id, "competency_count": len(competencies), "source": "conversation"})
        notice = f"总模型已生成，共 {len(competencies)} 项能力、{len(conflicts)} 个待处理冲突。"; reply = notice; result = {"model_id": model.id, "competencies": competencies, "conflicts": conflicts}
    elif tool == "CONFIRM_MODEL":
        model = db.scalar(select(ModelVersion).where(ModelVersion.project_id == project.id).order_by(ModelVersion.created_at.desc()))
        if not model: raise HTTPException(status_code=404, detail="项目尚未生成总模型")
        if model.status == ModelVersionStatus.CONFIRMED: raise HTTPException(status_code=409, detail="模型已经确认并冻结")
        draft = model.draft_json or {}
        if draft.get("manual_overrides"):
            competencies = draft.get("competencies", []); conflicts = draft.get("conflicts", [])
        else:
            jds = db.scalars(select(JobDescription).where(JobDescription.project_id == project.id, JobDescription.participates_in_model.is_(True))).all()
            items = [{"name": row.name, "jd_id": jd.id, "evidence_ids": row.evidence_ids, "weight": row.weight} for jd in jds for row in db.scalars(select(Competency).where(Competency.jd_id == jd.id)).all()]
            competencies = aggregate_competencies(items); conflicts = detect_conflicts(items)
        if conflicts: raise HTTPException(status_code=409, detail={"code": "BLOCKING_CONFLICTS", "conflicts": conflicts})
        payload = {"model_id": model.id, "project_id": project.id, "competencies": competencies, "conflict_count": 0}
        model.status = ModelVersionStatus.CONFIRMED; model.version = "v1.0"
        db.add(ModelSnapshot(model_version_id=model.id, version="v1.0", snapshot_json=payload))
        record_event(db, project.id, "MODEL_CONFIRMED", {"model_id": model.id, "version": "v1.0", "source": "conversation"})
        notice = "岗位胜任力模型已确认并冻结为 v1.0。"; reply = notice; result = {"model_id": model.id, "version": "v1.0"}
    else:
        raise HTTPException(status_code=422, detail=f"不支持的阶段一工具：{tool}")

    operation = {"action": tool, "requires_confirmation": False, "result": result}
    return {"reply": reply, "operation": operation, "system_notices": [notice] if notice else []}
