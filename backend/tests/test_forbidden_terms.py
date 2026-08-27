import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_forbidden_term_scan() -> None:
    result = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "scripts" / "check_forbidden_terms.py")],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
