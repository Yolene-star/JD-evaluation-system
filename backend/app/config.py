from dataclasses import dataclass
import os
from pathlib import Path


def load_local_env(path: Path) -> None:
    """Load simple KEY=VALUE settings without overwriting the shell environment."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and (not os.environ.get(key, "").strip() or key not in os.environ):
            os.environ[key] = value


LOCAL_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_local_env(LOCAL_ENV_PATH)


def get_llm_api_key(explicit: str | None = None) -> str | None:
    """Resolve the provider key at request time so long-lived servers pick up backend/.env."""
    if explicit:
        return explicit.strip() or None
    load_local_env(LOCAL_ENV_PATH)
    return os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")


def is_llm_analysis_enabled() -> bool:
    """Read the analysis toggle at request time for long-running local servers."""
    load_local_env(LOCAL_ENV_PATH)
    return os.getenv("LLM_ANALYSIS_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    app_name: str = "岗位胜任力测评与人才画像系统"
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")


settings = Settings()
