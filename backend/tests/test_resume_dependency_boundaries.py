import ast
from pathlib import Path


ROOT = Path(__file__).parents[1] / "app" / "services"


def _imports_resume(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "resume" or alias.name.startswith("resume.") for alias in node.names):
                return True
        if isinstance(node, ast.ImportFrom) and node.module and (
            node.module == "resume" or node.module.startswith("resume.") or "resume" in node.module
        ):
            return True
    return False


def test_state_scoring_and_evidence_package_are_resume_blind() -> None:
    for name in ("assessment_state.py", "scoring.py", "evidence_package.py"):
        assert not _imports_resume(ROOT / name)
