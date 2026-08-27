import argparse
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import create_database_engine
from app.generators.evidence_foundation.config import EvidenceFoundationConfig
from app.generators.forecasts.config import ForecastGenerationConfig
from app.generators.procurement.config import ProcurementGenerationConfig
from app.generators.scenarios.config import ScenarioGenerationConfig
from app.generators.signature import canonicalize
from app.models.platform import DatasetVersion
from app.services.forecast_generation import ForecastGenerationService


def summary(result):
    world = result.world
    dates = Counter(v.version_date for v in world.forecast_versions)
    totals = defaultdict(Decimal)
    for row in world.weekly_forecasts:
        totals[row.material_id] += row.forecast_qty
    return canonicalize({
        'notice': 'Synthetic data only. Aggregate forecast statistics; no per-record evaluation truth.',
        'dataset_status': 'GENERATING', 'counts': world.counts(),
        'valid_version_count': sum(v.is_valid for v in world.forecast_versions),
        'invalid_version_count': sum(not v.is_valid for v in world.forecast_versions),
        'same_day_revision_count': sum(n - 1 for n in dates.values()),
        'version_date_min': min(dates), 'version_date_max': max(dates),
        'week_1_start': min(r.week_start_date for r in world.weekly_forecasts),
        'week_13_start': max(r.week_start_date for r in world.weekly_forecasts),
        'zero_demand_material_count': sum(q == 0 for q in totals.values()),
        'forecast_content_hash': result.forecast_content_hash,
        'validation_status': result.validation_status,
    })


def main():
    parser = argparse.ArgumentParser(description='Derive shared synthetic forecast evidence')
    parser.add_argument('--dataset-version-name', default='demo-master-v1')
    parser.add_argument('--seed', type=int)
    for option in ('config', 'evidence-config', 'procurement-config', 'scenario-config', 'summary-output'):
        parser.add_argument('--' + option, type=Path)
    args = parser.parse_args()

    def load(path):
        return json.loads(path.read_text(encoding='utf-8')) if path else {}

    values = load(args.config)
    if args.seed is not None:
        values['seed'] = args.seed
    engine = create_database_engine(settings.database_url_generator.get_secret_value())
    try:
        with Session(engine, expire_on_commit=False) as session:
            dataset_id = session.scalar(select(DatasetVersion.dataset_version_id).where(DatasetVersion.version_name == args.dataset_version_name))
            session.rollback()
            if dataset_id is None:
                raise SystemExit('dataset version not found')
            result = ForecastGenerationService(session).generate(dataset_id, ForecastGenerationConfig(**values),
                evidence_config=EvidenceFoundationConfig(**load(args.evidence_config)),
                procurement_config=ProcurementGenerationConfig(**load(args.procurement_config)),
                scenario_config=ScenarioGenerationConfig(**load(args.scenario_config)))
        rendered = json.dumps(summary(result), ensure_ascii=False, indent=2, sort_keys=True)
        if args.summary_output:
            args.summary_output.write_text(rendered + '\n', encoding='utf-8')
        print(rendered)
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
