from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import create_database_engine
from app.generators.config import GenerationConfig
from app.generators.signature import canonicalize
from app.services.dataset_generation import DatasetGenerationService


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the deterministic Phase 2 master world")
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--snapshot-date", default="2026-08-26")
    parser.add_argument("--version-name", default="demo-master-v1")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--summary-output", type=Path)
    return parser.parse_args()


def _config(arguments: argparse.Namespace) -> GenerationConfig:
    values: dict[str, Any] = {}
    if arguments.config:
        values = json.loads(arguments.config.read_text(encoding="utf-8"))
    values.update(random_seed=arguments.seed, snapshot_date=arguments.snapshot_date)
    return GenerationConfig.demo(**values)


def _summary(result: Any, config: GenerationConfig) -> dict[str, Any]:
    world = result.world
    return canonicalize(
        {
            "notice": "Synthetic data only. Not derived from or suitable for real enterprise operations.",
            "dataset": {
                "dataset_version_id": result.dataset_version_id,
                "version_name": result.version_name,
                "snapshot_date": config.snapshot_date,
                "random_seed": config.random_seed,
                "status": "GENERATING",
                "generation_signature": result.generation_signature,
                "master_content_hash": result.master_content_hash,
                "validation_status": result.validation_status,
            },
            "counts": result.counts,
            "samples": {
                "organization_codes": sorted(row.organization_code for row in world.organizations)[:5],
                "employee_codes": sorted(row.employee_code for row in world.employees)[:5],
                "material_codes": sorted(row.material_code for row in world.materials)[:5],
                "project_codes": sorted(row.project_code for row in world.projects)[:5],
                "customer_codes": sorted(row.customer_code for row in world.customers)[:5],
                "supplier_codes": sorted(row.supplier_code for row in world.suppliers)[:5],
            },
            "relationship_counts": {
                name: result.counts[name]
                for name in (
                    "employee_role_assignments",
                    "material_projects",
                    "material_mpm_assignments",
                    "material_supplier_assignments",
                    "project_customers",
                    "material_responsibility_assignments",
                )
            },
        }
    )


def main() -> None:
    arguments = _arguments()
    config = _config(arguments)
    engine = create_database_engine(settings.database_url_generator.get_secret_value())
    try:
        with Session(engine, expire_on_commit=False) as session:
            result = DatasetGenerationService(session).generate(config, arguments.version_name)
        summary = _summary(result, config)
        rendered = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
        if arguments.summary_output:
            arguments.summary_output.parent.mkdir(parents=True, exist_ok=True)
            arguments.summary_output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
