import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8")


def test_runtime_data_and_credentials_are_ignored() -> None:
    paths = [
        ".env", "backend/.venv/probe", "postgres-data/PG_VERSION",
        "data/raw/probe.xlsx", "data/synthetic/probe.json",
        "backend/.pytest_cache/probe", "backend/app/__pycache__/probe.pyc",
    ]
    assert set(_git("check-ignore", "--no-index", *paths).splitlines()) == set(paths)
    tracked = _git("ls-files", "--cached", "-z").split("\0")
    assert not any(
        path == ".env" or path.startswith(("postgres-data/", "backend/.venv/"))
        for path in tracked
    )


def test_publishable_files_contain_no_local_paths_or_known_local_secrets() -> None:
    files = _git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")
    secrets = set()
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip("\"'")
            if "PASSWORD" in key or key.endswith(("_TOKEN", "_SECRET", "_API_KEY")):
                secrets.add(value)
            if "URL" in key and "://" in value:
                password = urlsplit(value).password
                if password:
                    secrets.add(unquote(password))
    secrets -= {"", "change_me", "<secret>"}
    findings = []
    for relative in files:
        if not relative or not (ROOT / relative).is_file():
            continue
        content = (ROOT / relative).read_bytes()
        text = content.decode("utf-8", errors="replace")
        if re.search(r"\b[A-Za-z]:[\\/](?![\\/])|/(?:Users|home)/[A-Za-z0-9_-]+/", text):
            findings.append(f"{relative}: local absolute path")
        if any(secret.encode("utf-8") in content for secret in secrets):
            findings.append(f"{relative}: local secret")
    # Report filenames only, never secret values or matching lines.
    assert not findings, "\n".join(findings)


def test_public_examples_have_no_per_record_truth() -> None:
    forbidden_keys = {
        "scenario_truth", "scenario_truth_rows", "scenario_truth_id", "scenario_pattern",
        "true_cause", "true_cause_subtype", "causal_project_id", "demand_change_type",
        "lifecycle_state", "stockpile_flag", "responsibility_type", "expected_action",
        "material_scenario_plans", "project_lifecycle_requirements",
    }

    def check(value):
        if isinstance(value, dict):
            assert not forbidden_keys.intersection(value)
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    files = list((ROOT / "examples").glob("*.json"))
    assert files
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "synthetic" in payload["notice"].lower()
        check(payload)
