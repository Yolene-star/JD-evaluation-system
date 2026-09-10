from .evidence import EvidenceTool
from .question import QuestionTool

__all__ = ["EvidenceTool", "QuestionTool", "ReportTool", "ScoringTool"]


def __getattr__(name: str):
    if name == "ReportTool":
        from .report import ReportTool

        return ReportTool
    if name == "ScoringTool":
        from .scoring import ScoringTool

        return ScoringTool
    raise AttributeError(name)
