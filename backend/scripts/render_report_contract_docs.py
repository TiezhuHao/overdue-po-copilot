"""Regenerate documentation projections without reading any workbook data rows."""
from pathlib import Path

from app.reporting.field_mapping import render_markdown as render_mapping
from app.reporting.report_header_manifest import render_markdown as render_headers


ROOT = Path(__file__).resolve().parents[2]
(ROOT / "docs" / "REPORT_HEADER_MANIFEST.md").write_text(render_headers(), encoding="utf-8")
(ROOT / "docs" / "REPORT_FIELD_MAPPING.md").write_text(render_mapping(), encoding="utf-8")
