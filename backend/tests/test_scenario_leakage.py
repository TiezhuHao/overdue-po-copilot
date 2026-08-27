import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


FORBIDDEN = {
    "scenario_truth",
    "true_cause",
    "true_cause_subtype",
    "causal_project_id",
    "demand_change_type",
    "responsibility_type",
    "expected_action",
}


def test_openapi_contains_no_hidden_truth_terms() -> None:
    rendered = json.dumps(TestClient(app).get("/openapi.json").json()).lower()
    assert all(term not in rendered for term in FORBIDDEN)


def test_public_api_and_schema_modules_do_not_import_evaluation_truth() -> None:
    app_root = Path(__file__).resolve().parents[1] / "app"
    files = [app_root / "main.py", app_root / "services" / "__init__.py", app_root / "services" / "readiness.py"]
    for relative in ("api", "schemas", "db", "repositories/reports", "services/report_queries", "services/exports"):
        directory = app_root / relative
        if directory.exists():
            files.extend(directory.rglob("*.py"))
    rendered = "\n".join(path.read_text(encoding="utf-8").lower() for path in files)
    assert all(term not in rendered for term in FORBIDDEN)


def test_public_app_does_not_load_private_modules_in_fresh_process() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import app.main; "
            "assert not any(name.startswith(('app.models.evaluation', "
            "'app.generators', 'app.services.scenario_generation')) for name in sys.modules)",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
