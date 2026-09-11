import json

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ChatMessage, Competency, Evidence, JobDescription, LLMCallLog, ModelVersion, Project
from ..services.llm import generate_reply
from ..services.audit import record_event
from ..services.analysis import analyze_project_jds
from ..services.commands import extract_pasted_jd
from ..services.stage1_intent import interpret_stage1_intent
from ..services.stage1_tools import execute_stage1_tool, preview_for

router = APIRouter(prefix="/api/projects", tags=["chat"])


def _save_message(db: Session, project_id: str, role: str, content: str) -> None:
    db.add(ChatMessage(project_id=project_id, role=role, content=content))


def _save_system_notice(db: Session, project_id: str, content: str) -> None:
    _save_message(db, project_id, "system", content)


@router.get("/{project_id}/chat/history")
def chat_history(project_id: str, db: Session = Depends(get_db)) -> dict:
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    rows = db.scalars(select(ChatMessage).where(ChatMessage.project_id == project_id).order_by(ChatMessage.created_at, ChatMessage.id)).all()
    return {"messages": [{"id": row.id, "role": row.role, "content": row.content, "created_at": row.created_at.isoformat()} for row in rows]}


@router.post("/{project_id}/chat")
def chat(project_id: str, payload: dict, db: Session = Depends(get_db), x_llm_api_key: str | None = Header(default=None)) -> dict:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    message = str(payload.get("message", "")).strip()
    if not message:
        raise HTTPException(status_code=422, detail="消息不能为空")
    _save_message(db, project.id, "user", message)
    pasted_jd = extract_pasted_jd(message)
    if pasted_jd and pasted_jd.requires_confirmation and not bool(payload.get("confirm", False)):
        title = pasted_jd.target or "对话导入 JD"
        reply = f"这段内容看起来可能是《{title}》的岗位描述。是否保存为新的 JD 并自动解析？"
        _save_message(db, project.id, "agent", reply)
        db.commit()
        return {
            "reply": reply,
            "source": "command-preview",
            "operation": {"action": "JD_INGESTED", "title": title, "requires_confirmation": True},
            "project_status": project.status,
        }
    if pasted_jd:
        title = pasted_jd.target or "对话导入 JD"
        jd = JobDescription(project_id=project.id, title=title[:200], raw_text=pasted_jd.text or message)
        db.add(jd)
        db.flush()
        record_event(db, project.id, "JD_ADDED", {"jd_id": jd.id, "title": jd.title, "source": "conversation"})
        analyze_project_jds(db, project, jd_ids={jd.id})
        notice = f"已从对话保存 JD：{jd.title}"
        analysis_notice = "JD 解析完成，单份 JD 模型已刷新"
        reply = f"已从对话保存并解析《{jd.title}》，单份 JD 模型已更新。"
        _save_message(db, project.id, "agent", reply)
        _save_system_notice(db, project.id, notice)
        _save_system_notice(db, project.id, analysis_notice)
        db.commit()
        return {
            "reply": reply,
            "source": "command",
            "operation": {"action": "JD_INGESTED", "jd_id": jd.id, "title": jd.title},
            "system_notices": [notice, analysis_notice],
            "project_status": project.status,
        }
    jds = db.scalars(select(JobDescription).where(JobDescription.project_id == project.id)).all()
    evidence = db.scalars(select(Evidence).join(JobDescription, Evidence.jd_id == JobDescription.id).where(JobDescription.project_id == project.id)).all()
    competency_names = sorted({item.name for jd in jds for item in db.scalars(select(Competency).where(Competency.jd_id == jd.id)).all()})
    latest_model = db.scalar(select(ModelVersion).where(ModelVersion.project_id == project.id).order_by(ModelVersion.created_at.desc()))
    if latest_model:
        competency_names = sorted(set(competency_names) | {str(item.get("name")) for item in (latest_model.draft_json or {}).get("competencies", []) if item.get("name")})
    context = {"project_name": project.name, "jds": [{"title": jd.title, "status": jd.status.value, "participates_in_model": jd.participates_in_model} for jd in jds], "competency_names": competency_names, "evidence": [{"id": item.id, "excerpt": item.excerpt} for item in evidence]}
    intent, intent_source, intent_latency, intent_error = interpret_stage1_intent(message, context, api_key=x_llm_api_key)
    if intent.tool != "CHAT":
        preview = preview_for(intent)
        if preview and not bool(payload.get("confirm", False)):
            _save_message(db, project.id, "agent", preview["reply"])
            db.add(LLMCallLog(project_id=project.id, task_type="stage1-intent", model="deepseek-chat" if intent_source == "llm-tool" else "deterministic-router", status=intent_source, latency_ms=intent_latency, error=intent_error))
            db.commit()
            return {**preview, "source": "command-preview", "project_status": project.status}
        tool_result = execute_stage1_tool(db, project, intent)
        _save_message(db, project.id, "agent", tool_result["reply"])
        for notice in tool_result["system_notices"]:
            _save_system_notice(db, project.id, notice)
        db.add(LLMCallLog(project_id=project.id, task_type="stage1-intent", model="deepseek-chat" if intent_source == "llm-tool" else "deterministic-router", status=intent_source, latency_ms=intent_latency, error=intent_error))
        db.commit()
        return {**tool_result, "source": intent_source, "project_status": project.status}
    reply, source, latency, error = generate_reply(project.name, project.status.value, message, context, api_key=x_llm_api_key)
    _save_message(db, project.id, "agent", reply)
    db.add(LLMCallLog(project_id=project.id, task_type="stage1-chat", model="deepseek-chat" if source == "llm" else "demo-fallback", status=source, latency_ms=latency, error=error))
    db.commit()
    return {"reply": reply, "source": source, "project_status": project.status, "error": error}
