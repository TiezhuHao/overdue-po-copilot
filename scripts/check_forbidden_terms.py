from __future__ import annotations

import re
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TERM_FILE = Path(__file__).with_name("forbidden_terms.txt")
SCAN_TARGETS = (
    REPOSITORY_ROOT / "backend" / "app",
    REPOSITORY_ROOT / "backend" / "tests",
    REPOSITORY_ROOT / "backend" / "alembic",
    REPOSITORY_ROOT / "examples",
    REPOSITORY_ROOT / "docs",
    REPOSITORY_ROOT / "frontend" / "app",
    REPOSITORY_ROOT / "frontend" / "components",
    REPOSITORY_ROOT / "frontend" / "lib",
    REPOSITORY_ROOT / "frontend" / "tests",
    REPOSITORY_ROOT / "README.md",
)
TEXT_SUFFIXES = {".py", ".md", ".ini", ".json", ".sql", ".txt", ".ts", ".tsx", ".css", ".mjs"}
APPROVED_DISPLAY_TERMS = {"BG", "PDT", "PCBA"}


def load_forbidden_terms() -> set[str]:
    if not TERM_FILE.exists():
        return set()
    terms = {
        line.strip()
        for line in TERM_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    return terms - APPROVED_DISPLAY_TERMS


def iter_text_files() -> list[Path]:
    files: list[Path] = []
    for target in SCAN_TARGETS:
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(
                path
                for path in target.rglob("*")
                if path.is_file()
                and path.suffix.lower() in TEXT_SUFFIXES
                and "__pycache__" not in path.parts
            )
    return sorted(files)


def scan() -> list[str]:
    forbidden_terms = load_forbidden_terms()
    findings: list[str] = []
    for path in iter_text_files():
        relative_path = path.relative_to(REPOSITORY_ROOT)
        content = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(content.splitlines(), start=1):
            for term in forbidden_terms:
                if re.search(re.escape(term), line, flags=re.IGNORECASE):
                    findings.append(f"{relative_path}:{line_number}: forbidden term '{term}'")
            if path.suffix.lower() == ".py" and re.search(r"\bKD\b", line):
                findings.append(f"{relative_path}:{line_number}: KD is not allowed in core code")
    return findings


def main() -> int:
    findings = scan()
    if findings:
        print("\n".join(findings))
        return 1
    print(f"Forbidden-term scan passed ({len(iter_text_files())} files scanned).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
