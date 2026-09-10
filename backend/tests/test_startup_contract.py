import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_unified_startup_reports_all_required_services() -> None:
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "start_project.ps1"),
            "-StatusOnly",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
    services = {row["name"]: row for row in json.loads(result.stdout)}
    assert services["backend"]["port"] == 8001
    assert services["frontend"]["port"] == 5192
    assert services["jd-collector"]["port"] == 8787
    assert services["jd-collector"]["install_url"] == "http://localhost:8787/install"
