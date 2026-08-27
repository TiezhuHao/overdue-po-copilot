from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import create_database_engine
from app.generators.scenarios.config import ScenarioGenerationConfig
from app.generators.signature import canonicalize
from app.models.platform import DatasetVersion
from app.services.scenario_generation import ScenarioGenerationService


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate isolated hidden Scenario Truth")
    parser.add_argument("--dataset-version-name", default="demo-master-v1")
    parser.add_argument("--seed", type=int, default=20260828)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--summary-output", type=Path)
    return parser.parse_args()


def _config(arguments: argparse.Namespace) -> ScenarioGenerationConfig:
    values: dict[str, Any] = {}
    if arguments.config:
        values = json.loads(arguments.config.read_text(encoding="utf-8"))
    values["scenario_seed"] = arguments.seed
    return ScenarioGenerationConfig.demo(**values)


def _summary(result: Any) -> dict[str, Any]:
    lines = {row.po_line_id: row for row in result.procurement.po_lines}
    pattern_counts = Counter(row.scenario_pattern for row in result.world.scenario_truth_rows)
    cause_counts = Counter(row.true_cause for row in result.world.scenario_truth_rows)
    mismatch_count = sum(
        lines[row.po_line_id].po_reference_project_id != row.causal_project_id
        for row in result.world.scenario_truth_rows
        if row.scenario_pattern != "TRIAL"
    )
    lifecycle_counts = Counter(result.world.project_lifecycle_requirements.values())
    return canonicalize(
        {
            "notice": (
                "Aggregate synthetic generator statistics only. Per-record evaluation "
                "truth remains isolated in the evaluation schema."
            ),
            "dataset_version_id": result.dataset_version_id,
            "overdue_truth_count": len(result.world.scenario_truth_rows),
            "scenario_pattern_counts": dict(sorted(pattern_counts.items())),
            "true_cause_counts": dict(sorted(cause_counts.items())),
            "reference_not_equal_causal_count": mismatch_count,
            "project_lifecycle_requirement_counts": dict(sorted(lifecycle_counts.items())),
            "scenario_content_hash": result.scenario_content_hash,
            "validation_status": result.validation_status,
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
            result = ScenarioGenerationService(session).generate(dataset_id, config)
        rendered = json.dumps(_summary(result), ensure_ascii=False, indent=2, sort_keys=True)
        if arguments.summary_output:
            arguments.summary_output.parent.mkdir(parents=True, exist_ok=True)
            arguments.summary_output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
