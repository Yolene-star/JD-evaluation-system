from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ModelSnapshot, ModelVersion, ModelVersionStatus


class ModelNotConfirmedError(ValueError):
    """Raised when assessment attempts to read a non-immutable stage-one model."""


@dataclass(frozen=True)
class ConfirmedCompetency:
    id: str
    name: str
    description: str
    weight: float
    jd_evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class ConfirmedModelSnapshot:
    model_version_id: str
    project_id: str
    version: str
    competencies: tuple[ConfirmedCompetency, ...]


def get_confirmed_model_snapshot(
    db: Session, project_id: str, model_version_id: str | None = None
) -> ConfirmedModelSnapshot:
    if model_version_id is not None and not model_version_id.strip():
        raise ModelNotConfirmedError("模型版本标识不能为空")
    query = select(ModelVersion).where(
        ModelVersion.project_id == project_id,
        ModelVersion.status == ModelVersionStatus.CONFIRMED,
    )
    if model_version_id is not None:
        query = query.where(ModelVersion.id == model_version_id)
    model = db.scalar(query.order_by(ModelVersion.created_at.desc()))
    if not model:
        raise ModelNotConfirmedError("阶段一模型尚未确认，无法开始阶段二")
    snapshot = db.scalar(select(ModelSnapshot).where(ModelSnapshot.model_version_id == model.id))
    if not snapshot:
        raise ModelNotConfirmedError("已确认模型缺少不可变快照")
    if not isinstance(snapshot.snapshot_json, Mapping):
        raise ModelNotConfirmedError("已确认模型快照格式无效")
    raw_items = snapshot.snapshot_json.get("competencies", [])
    if not isinstance(raw_items, list):
        raise ModelNotConfirmedError("已确认模型快照格式无效")
    try:
        parsed: list[ConfirmedCompetency] = []
        for index, item in enumerate(raw_items):
            if not isinstance(item, Mapping):
                raise ModelNotConfirmedError("已确认模型快照格式无效")
            weight = float(item.get("weight", 0.0))
            evidence_ids = item.get("jd_evidence_ids", item.get("evidence_ids", []))
            if not isfinite(weight) or weight < 0 or weight > 1 or not isinstance(evidence_ids, (list, tuple)):
                raise ModelNotConfirmedError("已确认模型快照格式无效")
            parsed.append(
                ConfirmedCompetency(
                    id=str(item.get("id") or f"{model.id}:{index}"),
                    name=str(item.get("name", "")),
                    description=str(item.get("description", "")),
                    weight=weight,
                    jd_evidence_ids=tuple(str(value) for value in evidence_ids),
                )
            )
        competencies = tuple(parsed)
    except (TypeError, ValueError) as error:
        raise ModelNotConfirmedError("已确认模型快照格式无效") from error
    if len(competencies) != len(raw_items):
        raise ModelNotConfirmedError("已确认模型快照格式无效")
    return ConfirmedModelSnapshot(
        model_version_id=model.id,
        project_id=project_id,
        version=snapshot.version,
        competencies=competencies,
    )


def create_assessment_session(db: Session, project_id: str, model_version_id: str) -> "AssessmentSession":
    from ..models import AssessmentSession

    get_confirmed_model_snapshot(db, project_id, model_version_id)
    session = AssessmentSession(project_id=project_id, model_version_id=model_version_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session
