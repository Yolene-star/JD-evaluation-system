import json

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ChatMessage, Evidence, JobDescription, LLMCallLog, Project
from ..services.llm import generate_reply
from ..services.audit import record_event
from ..services.analysis import analyze_project_jds
from ..services.commands import extract_pasted_jd, parse_command

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
    command = parse_command(message)
    if command.action == "REMOVE_JD":
        jd = next((item for item in db.query(JobDescription).filter(JobDescription.project_id == project.id).all() if item.title == command.target), None)
        if not jd:
            raise HTTPException(status_code=404, detail="未找到要移出的 JD")
        if not bool(payload.get("confirm", False)):
            reply = f"我找到《{jd.title}》，移出后它将不参与总模型，但原文和证据会保留。请确认是否移出。"
            _save_message(db, project.id, "agent", reply); db.commit()
            return {"reply": reply, "source": "command-preview", "operation": {"action": "REMOVE_JD", "jd_id": jd.id, "title": jd.title, "requires_confirmation": True}, "project_status": project.status}
        jd.participates_in_model = False
        record_event(db, project.id, "JD_REMOVED", {"jd_id": jd.id, "title": jd.title, "source": "conversation"})
        db.commit()
        return {"reply": f"已移出《{jd.title}》，原文和证据仍保留。", "source": "command", "operation": {"action": "REMOVE_JD", "jd_id": jd.id, "title": jd.title}, "project_status": project.status}
    if command.action == "EDIT_WEIGHT":
        reply = f"我可以将目标能力权重调整为 {command.value:g}%，但这会触发其他能力重新归一化。请在工作台确认后保存。"
        _save_message(db, project.id, "agent", reply); db.commit()
        return {"reply": reply, "source": "command-preview", "operation": {"action": "EDIT_WEIGHT", "value": command.value, "requires_confirmation": True}, "project_status": project.status}
    jds = db.scalars(select(JobDescription).where(JobDescription.project_id == project.id)).all()
    evidence = db.scalars(select(Evidence).join(JobDescription, Evidence.jd_id == JobDescription.id).where(JobDescription.project_id == project.id)).all()
    context = {"jds": [{"title": jd.title, "status": jd.status.value, "participates_in_model": jd.participates_in_model} for jd in jds], "evidence": [{"id": item.id, "excerpt": item.excerpt} for item in evidence]}
    reply, source, latency, error = generate_reply(project.name, project.status.value, message, context, api_key=x_llm_api_key)
    _save_message(db, project.id, "agent", reply)
    db.add(LLMCallLog(project_id=project.id, task_type="stage1-chat", model="deepseek-chat" if source == "llm" else "demo-fallback", status=source, latency_ms=latency, error=error))
    db.commit()
    return {"reply": reply, "source": source, "project_status": project.status, "error": error}
