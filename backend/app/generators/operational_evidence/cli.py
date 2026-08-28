"""Private generator CLI: aggregate-only output and sanitized errors."""
import argparse
import json
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.generators.evidence_foundation.config import EvidenceFoundationConfig
from app.generators.forecasts.config import ForecastGenerationConfig
from app.generators.procurement.config import ProcurementGenerationConfig
from app.generators.scenarios.config import ScenarioGenerationConfig
from app.generators.signature import canonicalize
from app.models.platform import DatasetVersion
from app.services.operational_evidence_generation import OperationalEvidenceGenerationService
from .config import OperationalEvidenceConfig


def summary(result):
    world = result.world
    return canonicalize({
        'notice': 'Synthetic data only; aggregate operational statistics without record-level evaluation truth.',
        'counts': world.counts(),
        'supply_component_count': sum(r.component_side == 'SUPPLY' for r in world.supply_demand_components),
        'demand_component_count': sum(r.component_side == 'DEMAND' for r in world.supply_demand_components),
        'positive_surplus_material_count': sum(r.supply_demand_surplus_qty > 0 for r in world.supply_demand_snapshots),
        'zero_surplus_material_count': sum(r.supply_demand_surplus_qty == 0 for r in world.supply_demand_snapshots),
        'negative_surplus_material_count': sum(r.supply_demand_surplus_qty < 0 for r in world.supply_demand_snapshots),
        'stockpile_date_min': min(v.version_date for v in world.stockpile_versions),
        'stockpile_date_max': max(v.version_date for v in world.stockpile_versions),
        'invalid_version_count': sum(not v.is_valid for v in world.stockpile_versions),
        'same_day_revision_count': len(world.stockpile_versions) - len({v.version_date for v in world.stockpile_versions}),
        **result.validation_summary,
        'operational_content_hash': result.operational_content_hash,
        'dataset_status': 'GENERATING', 'validation_status': result.validation_status,
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset-version-name', default='demo-master-v1')
    parser.add_argument('--seed', type=int)
    for option in ('config', 'evidence-config', 'forecast-config', 'procurement-config', 'scenario-config', 'summary-output'):
        parser.add_argument('--' + option, type=Path)
    args = parser.parse_args()

    def load(path):
        return json.loads(path.read_text(encoding='utf-8')) if path else {}

    values = load(args.config)
    if args.seed is not None:
        values['seed'] = args.seed
    engine = create_engine(settings.database_url_generator.get_secret_value(), hide_parameters=True, pool_pre_ping=True)
    try:
        with Session(engine, expire_on_commit=False) as session:
            did = session.scalar(select(DatasetVersion.dataset_version_id).where(DatasetVersion.version_name == args.dataset_version_name))
            session.rollback()
            if did is None:
                raise ValueError('DATASET_NOT_FOUND')
            result = OperationalEvidenceGenerationService(session).generate(
                did, OperationalEvidenceConfig(**values),
                evidence_config=EvidenceFoundationConfig(**load(args.evidence_config)),
                forecast_config=ForecastGenerationConfig(**load(args.forecast_config)),
                procurement_config=ProcurementGenerationConfig(**load(args.procurement_config)),
                scenario_config=ScenarioGenerationConfig(**load(args.scenario_config)))
        rendered = json.dumps(summary(result), indent=2, ensure_ascii=False, sort_keys=True)
        if args.summary_output:
            args.summary_output.write_text(rendered + '\n', encoding='utf-8')
        print(rendered)
    except Exception as exc:
        # Never print SQL parameters, credentials or per-record evaluation data.
        raise SystemExit('Operational generation failed: ' + type(exc).__name__) from None
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
