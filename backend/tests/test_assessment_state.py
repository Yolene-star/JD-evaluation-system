from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import (
    AssessmentCompletion,
    AssessmentEvent,
    AssessmentSession,
    AssessmentSessionStatus,
    CompetencyAssessment,
    CompetencyAssessmentStatus,
    ModelVersion,
    ModelVersionStatus,
    Project,
)
from backend.app.services.assessment_contracts import (
    ConfirmedCompetency,
    ConfirmedModelSnapshot,
)
from backend.app.services.assessment_events import record_event
from backend.app.services.assessment_state import (
    InvalidAssessmentTransition,
    apply_analysis,
    finish_session,
    pause_session,
    resume_session,
    select_question_scope,
    start_session,
)


test_engine = create_engine("sqlite://", poolclass=StaticPool)
TestSession = sessionmaker(bind=test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def tables() -> None:
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)


@pytest.fixture
def snapshot() -> ConfirmedModelSnapshot:
    return ConfirmedModelSnapshot(
        model_version_id="model-1",
        project_id="project-1",
        version="v1.0",
        competencies=(
            ConfirmedCompetency("c-1", "系统设计", "", 0.5, ("e-1",)),
            ConfirmedCompetency("c-2", "问题分析", "", 0.3, ("e-2",)),
            ConfirmedCompetency("c-3", "沟通表达", "", 0.2, ("e-3",)),
        ),
    )


@pytest.fixture
def db_and_session() -> tuple[object, AssessmentSession]:
    db = TestSession()
    db.add(Project(id="project-1", name="状态机测试"))
    db.add(ModelVersion(id="model-1", project_id="project-1", status=ModelVersionStatus.CONFIRMED))
    db.flush()
    assessment_session = AssessmentSession(id="session-1", project_id="project-1", model_version_id="model-1")
    db.add(assessment_session)
    db.flush()
    yield db, assessment_session
    db.close()


def insufficient_analysis() -> SimpleNamespace:
    return SimpleNamespace(evidence_sufficiency="INSUFFICIENT")


def sufficient_analysis() -> SimpleNamespace:
    return SimpleNamespace(evidence_sufficiency="SUFFICIENT")


def _assessments(db: object, assessment_session: AssessmentSession) -> list[CompetencyAssessment]:
    return list(
        db.scalars(
            select(CompetencyAssessment)
            .where(CompetencyAssessment.session_id == assessment_session.id)
            .order_by(CompetencyAssessment.created_at, CompetencyAssessment.id)
        )
    )


def test_start_initializes_stable_order_and_first_question(snapshot, db_and_session) -> None:
    db, assessment_session = db_and_session

    transition = start_session(db, assessment_session, snapshot)

    items = _assessments(db, assessment_session)
    assert transition.next_action == "ASK_MAIN_QUESTION"
    assert assessment_session.status is AssessmentSessionStatus.IN_PROGRESS
    assert [item.competency_id for item in items] == ["c-1", "c-2", "c-3"]
    assert items[0].status is CompetencyAssessmentStatus.ASKING
    assert assessment_session.current_competency_id == "c-1"


def test_pause_resume_finish_and_invalid_transitions(snapshot, db_and_session) -> None:
    db, assessment_session = db_and_session
    with pytest.raises(InvalidAssessmentTransition):
        pause_session(assessment_session)

    start_session(db, assessment_session, snapshot)
    assert pause_session(assessment_session).current_status is AssessmentSessionStatus.PAUSED
    assert resume_session(assessment_session).current_status is AssessmentSessionStatus.IN_PROGRESS
    assert finish_session(assessment_session, "user ended").next_action == "PARTIALLY_FINISHED"
    assert assessment_session.status is AssessmentSessionStatus.PARTIALLY_FINISHED
    assert assessment_session.completion is AssessmentCompletion.PARTIAL
    assert {item.status for item in _assessments(db, assessment_session)} == {CompetencyAssessmentStatus.INCOMPLETE}
    with pytest.raises(InvalidAssessmentTransition):
        resume_session(assessment_session)


def test_insufficient_answers_create_only_two_targeted_follow_ups_then_exhaust(snapshot, db_and_session) -> None:
    db, assessment_session = db_and_session
    start_session(db, assessment_session, snapshot)
    first = _assessments(db, assessment_session)[0]

    assert apply_analysis(assessment_session, first, insufficient_analysis()).next_action == "ASK_FOLLOW_UP"
    assert first.follow_up_count == 1
    assert first.status is CompetencyAssessmentStatus.FOLLOW_UP
    assert apply_analysis(assessment_session, first, insufficient_analysis()).next_action == "ASK_FOLLOW_UP"
    assert first.follow_up_count == 2
    assert apply_analysis(assessment_session, first, insufficient_analysis()).next_action == "ASK_MAIN_QUESTION"
    assert first.status is CompetencyAssessmentStatus.EXHAUSTED
    assert first.follow_up_count == 2
    assert assessment_session.current_competency_id == "c-2"


def test_sufficient_analysis_advances_and_completes_full_only_when_none_pending(snapshot, db_and_session) -> None:
    db, assessment_session = db_and_session
    start_session(db, assessment_session, snapshot)
    first, second, third = _assessments(db, assessment_session)

    assert apply_analysis(assessment_session, first, sufficient_analysis()).next_action == "ASK_MAIN_QUESTION"
    assert assessment_session.status is AssessmentSessionStatus.IN_PROGRESS
    assert apply_analysis(assessment_session, second, sufficient_analysis()).next_action == "ASK_MAIN_QUESTION"
    transition = apply_analysis(assessment_session, third, sufficient_analysis())

    assert transition.next_action == "COMPLETE"
    assert assessment_session.status is AssessmentSessionStatus.COMPLETED
    assert assessment_session.completion is AssessmentCompletion.FULL
    assert assessment_session.current_competency_id is None


def test_composite_targets_advance_independently(snapshot, db_and_session) -> None:
    db, assessment_session = db_and_session
    start_session(db, assessment_session, snapshot)
    first, second, third = _assessments(db, assessment_session)

    assert select_question_scope(snapshot, [first, second, third]) == ["c-1", "c-2", "c-3"]
    apply_analysis(assessment_session, first, sufficient_analysis())
    apply_analysis(assessment_session, second, insufficient_analysis())

    assert first.status is CompetencyAssessmentStatus.SUFFICIENT
    assert second.status is CompetencyAssessmentStatus.FOLLOW_UP
    assert third.status is CompetencyAssessmentStatus.PENDING
    assert assessment_session.status is AssessmentSessionStatus.IN_PROGRESS
    assert select_question_scope(snapshot, [first, second, third]) == ["c-2", "c-3"]


def test_apply_analysis_rejects_terminal_competency_without_mutating_state(snapshot, db_and_session) -> None:
    db, assessment_session = db_and_session
    start_session(db, assessment_session, snapshot)
    first = _assessments(db, assessment_session)[0]
    apply_analysis(assessment_session, first, sufficient_analysis())
    with pytest.raises(InvalidAssessmentTransition, match="terminal competency"):
        apply_analysis(assessment_session, first, sufficient_analysis())
    assert assessment_session.current_competency_id == "c-2"


def test_events_are_append_only_json_records_in_write_order(db_and_session) -> None:
    db, assessment_session = db_and_session
    first = record_event(db, assessment_session.id, "ASSESSMENT_STARTED", {"source": "test"})
    second = record_event(db, assessment_session.id, "ASSESSMENT_PAUSED", {"reason": "break"})
    db.flush()

    events = list(
        db.scalars(
            select(AssessmentEvent)
            .where(AssessmentEvent.session_id == assessment_session.id)
            .order_by(AssessmentEvent.created_at, AssessmentEvent.id)
        )
    )
    assert [event.id for event in events] == [first.id, second.id]
    assert [event.action for event in events] == ["ASSESSMENT_STARTED", "ASSESSMENT_PAUSED"]
    assert [event.payload for event in events] == ['{"source": "test"}', '{"reason": "break"}']
