import os
from pathlib import Path


# Unit/integration tests must never spend a developer's real API quota.
# Tests that cover AI analysis explicitly enable it and replace the network boundary.
os.environ["LLM_ANALYSIS_ENABLED"] = "0"

# Tests importing the real FastAPI app must never connect to the developer database.
test_data_dir = Path(__file__).resolve().parents[2] / ".pytest-run"
test_data_dir.mkdir(exist_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{(test_data_dir / f'app-{os.getpid()}.db').as_posix()}"
