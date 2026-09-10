from collections.abc import Callable
from typing import Any

from ...services.report_service import generate_report


class ReportTool:
    def __init__(self, generate_fn: Callable[..., Any] = generate_report) -> None:
        self.generate_fn = generate_fn

    def generate(
        self,
        *,
        db: Any,
        session_id: str,
        evidence_package_id: str,
        evidence_package: dict,
        rubric_set_id: str,
        idempotency_key: str,
        narrative_adapter: Any = None,
    ) -> Any:
        return self.generate_fn(
            db,
            session_id,
            evidence_package_id,
            evidence_package,
            rubric_set_id,
            idempotency_key,
            narrative_adapter=narrative_adapter,
        )
