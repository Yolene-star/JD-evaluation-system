from pathlib import Path


def test_alembic_scaffold_declares_metadata_environment():
    root = Path(__file__).parents[1]
    assert (root / "alembic.ini").exists()
    env = (root / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "target_metadata = Base.metadata" in env
    assert (root / "alembic" / "versions").is_dir()
