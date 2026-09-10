from urllib.parse import urlparse
from html.parser import HTMLParser
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent, ChatMessage, JobDescription, JobDescriptionStatus, Project
from ..schemas import JdUpdate, JobDescriptionResponse, LinkJdCreate, TextJdCreate
from ..services.audit import record_event
from ..services.analysis import analyze_project_jds
from ..services.jd_extraction import extract_html, select_adapter

router = APIRouter(tags=["job-descriptions"])


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.parts: list[str] = []
    def handle_data(self, data: str) -> None:
        if data.strip(): self.parts.append(data.strip())


def extract_public_page(url: str) -> tuple[str, str, str]:
    request = Request(url, headers={"User-Agent": "competency-assessment-demo/1.0"})
    with urlopen(request, timeout=15) as response:
        raw = response.read(500_000)
    result = extract_html(url, raw.decode("utf-8", errors="replace"))
    if not result.text: raise HTTPException(status_code=422, detail="网页未提取到可用正文")
    return result.title, result.text[:500_000], result.adapter


def project_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def add_jd(db: Session, project: Project, title: str, text: str, *, source: str = "text") -> JobDescription:
    if not title.strip() or not text.strip():
        raise HTTPException(status_code=422, detail="JD标题和正文不能为空")
    if len(text) > 500_000:
        raise HTTPException(status_code=413, detail="JD正文超过大小限制")
    jd = JobDescription(project_id=project.id, title=title.strip(), raw_text=text)
    db.add(jd)
    db.flush()
    record_event(db, project.id, "JD_ADDED", {"jd_id": jd.id, "title": jd.title, "source": source})
    db.commit()
    db.refresh(jd)
    return jd


@router.post("/api/projects/{project_id}/jds/text", response_model=JobDescriptionResponse, status_code=status.HTTP_201_CREATED)
def add_text_jd(project_id: str, payload: TextJdCreate, db: Session = Depends(get_db)) -> JobDescription:
    return add_jd(db, project_or_404(db, project_id), payload.title, payload.text)


@router.post("/api/projects/{project_id}/jds/file", response_model=JobDescriptionResponse, status_code=status.HTTP_201_CREATED)
async def add_file_jd(project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)) -> JobDescription:
    project = project_or_404(db, project_id)
    if file.content_type not in {"text/plain", "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}:
        raise HTTPException(status_code=415, detail="仅支持 TXT、PDF 或 DOCX 文件")
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("utf-8", errors="replace")
    return add_jd(db, project, file.filename or "未命名JD", text)


@router.post("/api/projects/{project_id}/jds/link", response_model=JobDescriptionResponse, status_code=status.HTTP_201_CREATED)
def add_link_jd(project_id: str, payload: LinkJdCreate, db: Session = Depends(get_db)) -> JobDescription:
    project = project_or_404(db, project_id)
    parsed = urlparse(payload.url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="链接必须是公开的 http/https 地址")
    try:
        title, text, adapter = extract_public_page(payload.url)
    except HTTPException:
        raise
    except OSError as exc:
        adapter_name = select_adapter(payload.url).name
        label = {"boss-zhipin": "Boss 直聘", "mokahr": "Mokahr ATS", "universal": "通用网页"}.get(adapter_name, adapter_name)
        raise HTTPException(status_code=502, detail=f"网页提取失败：已识别为“{label}”模块，但当前环境无法直接访问该网页；请在该网页使用“浏览器提取”模块。") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"网页提取失败：{str(exc)[:160]}") from exc
    jd = add_jd(db, project, title or payload.url, text)
    record_event(db, project.id, "JD_EXTRACTOR_SELECTED", {"jd_id": jd.id, "adapter": adapter, "source_url": payload.url})
    db.commit()
    db.refresh(jd)
    return jd

@router.post("/api/projects/{project_id}/jds/browser", response_model=JobDescriptionResponse, status_code=status.HTTP_201_CREATED)
def add_browser_jd(project_id: str, payload: dict, db: Session = Depends(get_db)) -> JobDescription:
    project = project_or_404(db, project_id)
    extracted = payload.get("extracted") if isinstance(payload.get("extracted"), dict) else payload
    title = str(extracted.get("job_title") or payload.get("page_title") or "网页岗位").strip()
    text = str(extracted.get("description") or payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="当前网页未提取到 JD 正文")
    jd = add_jd(db, project, title, text, source="browser")
    analyze_project_jds(db, project, jd_ids={jd.id})
    db.add(ChatMessage(project_id=project.id, role="system", content=f"已从浏览器提取并保存 JD：{jd.title}；单份 JD 模型已刷新。"))
    db.commit()
    db.refresh(jd)
    return jd


@router.get("/api/projects/{project_id}/events")
def list_events(project_id: str, db: Session = Depends(get_db)) -> list[dict]:
    project_or_404(db, project_id)
    events = db.scalars(select(AuditEvent).where(AuditEvent.project_id == project_id).order_by(AuditEvent.created_at.desc())).all()
    return [{"id": event.id, "action": event.action, "payload": event.payload, "created_at": event.created_at} for event in events]


@router.patch("/api/jds/{jd_id}", response_model=JobDescriptionResponse)
def update_jd(jd_id: str, payload: JdUpdate, db: Session = Depends(get_db)) -> JobDescription:
    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="JD不存在")
    if payload.title is not None:
        if not payload.title.strip():
            raise HTTPException(status_code=422, detail="JD标题不能为空")
        jd.title = payload.title.strip()
    if payload.participates_in_model is not None:
        jd.participates_in_model = payload.participates_in_model
    record_event(db, jd.project_id, "JD_UPDATED", {"jd_id": jd.id, "title": jd.title})
    db.commit()
    db.refresh(jd)
    return jd


@router.post("/api/jds/{jd_id}/readd", response_model=JobDescriptionResponse)
def readd_jd(jd_id: str, db: Session = Depends(get_db)) -> JobDescription:
    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="JD不存在")
    jd.participates_in_model = True
    record_event(db, jd.project_id, "JD_READD", {"jd_id": jd.id})
    db.commit()
    db.refresh(jd)
    return jd


@router.post("/api/jds/{jd_id}/retry")
def retry_jd(jd_id: str, db: Session = Depends(get_db)) -> dict:
    jd = db.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="JD不存在")
    jd.status = JobDescriptionStatus.RECEIVED
    db.commit()
    return {"id": jd.id, "status": jd.status}


@router.get("/api/jds/{jd_id}/failure")
def jd_failure(jd_id: str, db: Session = Depends(get_db)) -> dict:
    jd = db.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="JD不存在")
    if jd.status != JobDescriptionStatus.FAILED:
        return {"id": jd.id, "status": jd.status, "failure": None, "recovery_actions": []}
    return {"id": jd.id, "status": jd.status, "failure": {"stage": "parsing", "reason": "解析失败"}, "recovery_actions": ["retry", "reupload", "paste_text"]}
