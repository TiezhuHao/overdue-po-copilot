import argparse
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import create_database_engine
from app.generators.evidence_foundation.calendar import active
from app.generators.evidence_foundation.config import EvidenceFoundationConfig
from app.generators.evidence_foundation.world import DemandObservationIndex
from app.generators.procurement.config import ProcurementGenerationConfig
from app.generators.scenarios.config import ScenarioGenerationConfig
from app.generators.signature import canonicalize
from app.models.platform import DatasetVersion
from app.services.evidence_foundation_generation import EvidenceFoundationGenerationService


def summary(result):
    world = result.world
    index = DemandObservationIndex(world)
    total = sum((sum(index.observe(signal.demand_signal_id, result.snapshot_date).values()) for signal in world.demand_signals), Decimal(0))
    return canonicalize({
        "notice": "Synthetic data only. Aggregate evidence statistics; no per-record evaluation truth.",
        "dataset_version_id": result.dataset_version_id,
        "dataset_status": "GENERATING",
        "counts": world.counts(),
        "snapshot_lifecycle_distribution": dict(Counter(row.lifecycle_stage for row in world.project_lifecycle_history if active(row, result.snapshot_date))),
        "demand_date_min": min(row.demand_date for row in world.demand_signal_points),
        "demand_date_max": max(row.demand_date for row in world.demand_signal_points),
        "total_synthetic_demand_qty": total,
        "quantity_observed_as_of": result.snapshot_date,
        "evidence_foundation_content_hash": result.evidence_foundation_content_hash,
        "validation_status": result.validation_status,
    })


def main():
    parser = argparse.ArgumentParser(description="Generate shared synthetic evidence foundation")
    parser.add_argument("--dataset-version-name", default="demo-master-v1")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--scenario-config", type=Path)
    parser.add_argument("--procurement-config", type=Path)
    parser.add_argument("--summary-output", type=Path)
    args = parser.parse_args()

    def load(path):
        return json.loads(path.read_text(encoding="utf-8")) if path else {}

    values = load(args.config)
    if args.seed is not None:
        values["evidence_seed"] = args.seed
    config = EvidenceFoundationConfig(**values)
    engine = create_database_engine(settings.database_url_generator.get_secret_value())
    try:
        with Session(engine, expire_on_commit=False) as session:
            dataset_id = session.scalar(select(DatasetVersion.dataset_version_id).where(DatasetVersion.version_name == args.dataset_version_name))
            session.rollback()
            if dataset_id is None:
                raise SystemExit("dataset version not found")
            result = EvidenceFoundationGenerationService(session).generate(
                dataset_id, config, procurement_config=ProcurementGenerationConfig(**load(args.procurement_config)),
                scenario_config=ScenarioGenerationConfig(**load(args.scenario_config)),
            )
        rendered = json.dumps(summary(result), ensure_ascii=False, indent=2, sort_keys=True)
        if args.summary_output:
            args.summary_output.parent.mkdir(parents=True, exist_ok=True)
            args.summary_output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
