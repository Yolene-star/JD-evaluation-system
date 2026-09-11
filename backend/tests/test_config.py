import os

from backend.app.config import get_llm_api_key, load_local_env, settings


def test_pytest_uses_an_isolated_database() -> None:
    assert ".pytest-run" in settings.database_url


def test_load_local_env_reads_key_value_pairs_without_overwriting_environment(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=local-secret\nLLM_MODEL=deepseek-chat\n", encoding="utf-8")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODEL", "environment-model")
    load_local_env(env_file)
    assert os.environ["DEEPSEEK_API_KEY"] == "local-secret"
    assert os.environ["LLM_MODEL"] == "environment-model"


def test_llm_key_can_be_resolved_after_process_start(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=runtime-secret\n", encoding="utf-8")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    import backend.app.config as config
    monkeypatch.setattr(config, "LOCAL_ENV_PATH", env_file)
    assert get_llm_api_key() == "runtime-secret"


def test_load_local_env_accepts_utf8_bom(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=bom-secret\n", encoding="utf-8-sig")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    load_local_env(env_file)
    assert os.environ["DEEPSEEK_API_KEY"] == "bom-secret"
import os

from backend.app.config import load_local_env


def test_load_local_env_fills_empty_environment_values(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("HTTPS_PROXY=http://127.0.0.1:7890\n", encoding="utf-8")
    monkeypatch.setenv("HTTPS_PROXY", "")

    load_local_env(env_file)

    assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:7890"
