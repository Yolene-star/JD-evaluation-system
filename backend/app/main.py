from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from .config import settings
from .db import Base, engine
from .schemas import HealthResponse

# Import models before create_all so SQLAlchemy registers every table.
from . import models  # noqa: F401,E402


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5192", "http://localhost:5192"], allow_methods=["POST", "OPTIONS"], allow_headers=["*"])

    @app.on_event("startup")
    def initialize_database() -> None:
        Base.metadata.create_all(bind=engine)
        # Keep the local SQLite demo database compatible with additive model fields.
        if settings.database_url.startswith("sqlite"):
            columns = {column["name"] for column in inspect(engine).get_columns("competencies")}
            if "description" not in columns:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE competencies ADD COLUMN description TEXT NOT NULL DEFAULT ''"))
            assessment_columns = {
                "assessment_sessions": {
                    "completion": "TEXT NOT NULL DEFAULT 'NONE'",
                    "started_at": "DATETIME",
                    "paused_at": "DATETIME",
                    "completed_at": "DATETIME",
                },
                "competency_assessments": {
                    "created_at": "DATETIME",
                    "main_question": "TEXT",
                    "evidence_sufficiency": "TEXT NOT NULL DEFAULT 'UNCERTAIN'",
                    "started_at": "DATETIME",
                    "completed_at": "DATETIME",
                },
                "assessment_turns": {"turn_index": "INTEGER NOT NULL DEFAULT 0", "competency_assessment_id": "TEXT"},
                "evidence_observations": {
                    "competency_assessment_id": "TEXT",
                    "summary": "TEXT NOT NULL DEFAULT ''",
                    "source_excerpt": "TEXT",
                    "created_at": "DATETIME",
                },
            }
            with engine.begin() as connection:
                for table, additions in assessment_columns.items():
                    existing = {column["name"] for column in inspect(engine).get_columns(table)}
                    for name, definition in additions.items():
                        if name not in existing:
                            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app


app = create_app()
from .routes import analysis, assessments, chat, confirmation, evidence_packages, export, jds, models, projects, reports, resume_contexts, rubrics  # noqa: E402

app.include_router(projects.router)
app.include_router(jds.router)
app.include_router(resume_contexts.router)
app.include_router(analysis.router)
app.include_router(models.router)
app.include_router(confirmation.router)
app.include_router(export.router)
app.include_router(chat.router)
app.include_router(assessments.router)
app.include_router(evidence_packages.router)
app.include_router(reports.router)
app.include_router(rubrics.router)
