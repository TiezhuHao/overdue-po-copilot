from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import create_database_engine
from app.domain.procurement import is_overdue
from app.generators.procurement.config import ProcurementGenerationConfig
from app.generators.signature import canonicalize
from app.models.platform import DatasetVersion
from app.services.procurement_generation import ProcurementGenerationService


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate deterministic Phase 3 procurement facts")
    parser.add_argument("--dataset-version-name", default="demo-master-v1")
    parser.add_argument("--seed", type=int, default=20260827)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--summary-output", type=Path)
    return parser.parse_args()


def _config(arguments: argparse.Namespace) -> ProcurementGenerationConfig:
    values: dict[str, Any] = {}
    if arguments.config:
        values = json.loads(arguments.config.read_text(encoding="utf-8"))
    values["random_seed"] = arguments.seed
    return ProcurementGenerationConfig.demo(**values)


def _summary(result: Any) -> dict[str, Any]:
    organizations = {row.organization_id: row for row in result.master.organizations}
    materials = {row.material_id: row for row in result.master.materials}
    projects = {row.project_id: row for row in result.master.projects}
    headers = {row.po_header_id: row for row in result.world.po_headers}
    lines = {row.po_line_id: row for row in result.world.po_lines}
    trial_count = sum(
        organizations[row.inventory_organization_id].inventory_organization_type == "TRIAL"
        for row in result.world.po_headers
    )
    overdue_count = sum(
        is_overdue(
            result.snapshot_date,
            lines[row.po_line_id].order_date,
            lines[row.po_line_id].material_lt_days_at_order,
        )
        for row in result.world.po_line_schedules
    )
    examples = []
    for line in sorted(
        result.world.po_lines,
        key=lambda row: (headers[row.po_header_id].po_number, row.po_line_number),
    )[:5]:
        header = headers[line.po_header_id]
        examples.append(
            {
                "po_number": header.po_number,
                "po_line_number": line.po_line_number,
                "material_code": materials[line.material_id].material_code,
                "reference_project_code": projects[line.po_reference_project_id].project_code,
            }
        )
    return canonicalize(
        {
            "notice": "Synthetic data only. No proprietary enterprise data included.",
            "dataset_version_id": result.dataset_version_id,
            "dataset_version_name": result.dataset_version_name,
            "dataset_status": "GENERATING",
            "counts": result.counts,
            "inventory_organization_distribution": {
                "TRIAL": trial_count,
                "MASS_PRODUCTION": len(result.world.po_headers) - trial_count,
            },
            "objective_age_distribution": {
                "overdue_candidate_schedules": overdue_count,
                "non_overdue_schedules": len(result.world.po_line_schedules) - overdue_count,
            },
            "synthetic_po_examples": examples,
            "validation_status": result.validation_status,
            "procurement_content_hash": result.procurement_content_hash,
        }
    )


def main() -> None:
    arguments = _arguments()
    config = _config(arguments)
    engine = create_database_engine(settings.database_url_generator.get_secret_value())
    try:
        with Session(engine, expire_on_commit=False) as session:
            dataset_id = session.scalar(
                select(DatasetVersion.dataset_version_id).where(
                    DatasetVersion.version_name == arguments.dataset_version_name
                )
            )
            if dataset_id is None:
                raise SystemExit("dataset version not found")
            session.rollback()
            result = ProcurementGenerationService(session).generate(dataset_id, config)
        rendered = json.dumps(_summary(result), ensure_ascii=False, indent=2, sort_keys=True)
        if arguments.summary_output:
            arguments.summary_output.parent.mkdir(parents=True, exist_ok=True)
            arguments.summary_output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
