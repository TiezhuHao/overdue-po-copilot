import json
import re
import subprocess
import struct
import zlib
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]


def _publishable_text(content: bytes) -> str:
    """Scan screenshot metadata as text, not arbitrary compressed pixel bytes."""
    if content.startswith(b"\xff\xd8"):
        chunks, offset = [], 2
        while offset + 4 <= len(content):
            assert content[offset] == 255, "invalid JPEG marker"
            marker = content[offset + 1]
            if marker in (0xDA, 0xD9):  # Compressed scan / end of image.
                break
            size = int.from_bytes(content[offset + 2:offset + 4], "big")
            assert size >= 2 and offset + size + 2 <= len(content), "truncated JPEG metadata"
            if 0xE0 <= marker <= 0xEF or marker == 0xFE:
                chunks.append(content[offset + 4:offset + size + 2])
            offset += size + 2
        return b"\n".join(chunks).decode("utf-8", errors="replace")
    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        return content.decode("utf-8", errors="replace")
    chunks, offset = [], 8
    while offset + 12 <= len(content):
        size = struct.unpack_from(">I", content, offset)[0]
        kind = content[offset + 4:offset + 8]
        value = content[offset + 8:offset + 8 + size]
        assert len(value) == size, "truncated PNG chunk"
        if kind == b"tEXt":
            chunks.append(value)
        elif kind == b"zTXt":
            keyword, encoded = value.split(b"\0", 1)
            chunks.extend((keyword, zlib.decompress(encoded[1:])))
        elif kind == b"iTXt":
            keyword, encoded = value.split(b"\0", 1)
            flag = encoded[0]
            language, translated, message = encoded[2:].split(b"\0", 2)
            chunks.extend((keyword, language, translated, zlib.decompress(message) if flag else message))
        elif kind != b"IDAT":
            # Retain non-pixel ancillary metadata, including EXIF, for the scan.
            chunks.append(value)
        offset += size + 12
    return b"\n".join(chunks).decode("utf-8", errors="replace")


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
        text = _publishable_text(content)
        if re.search(r"\b[A-Za-z]:[\\/](?![\\/])|/(?:Users|home)/[A-Za-z0-9_-]+/", text):
            findings.append(f"{relative}: local absolute path")
        if any(secret.encode("utf-8") in content or secret in text for secret in secrets):
            findings.append(f"{relative}: local secret")
    # Report filenames only, never secret values or matching lines.
    assert not findings, "\n".join(findings)


def test_png_scan_preserves_plain_and_compressed_metadata():
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + b"\0" * 4
    metadata = b"metadata-sensitive-marker"
    sample = (b"\x89PNG\r\n\x1a\n" + chunk(b"IDAT", b"pixel-bytes")
              + chunk(b"tEXt", b"note\0" + metadata)
              + chunk(b"zTXt", b"note\0\0" + zlib.compress(metadata))
              + chunk(b"iTXt", b"note\0\1\0\0\0" + zlib.compress(metadata)))
    text = _publishable_text(sample)
    assert text.count(metadata.decode()) == 3 and "pixel-bytes" not in text


def test_jpeg_scan_preserves_metadata_without_scanning_pixel_stream():
    metadata = b"metadata-sensitive-marker"
    sample = b"\xff\xd8\xff\xfe" + (len(metadata) + 2).to_bytes(2, "big") + metadata
    sample += b"\xff\xda\x00\x02pixel-bytes"
    assert _publishable_text(sample) == metadata.decode()


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
