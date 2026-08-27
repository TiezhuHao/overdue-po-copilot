from dataclasses import dataclass

from sqlalchemy import func, insert, select

from app.generators.evidence_foundation.config import EvidenceFoundationConfig
from app.generators.evidence_foundation.world import EvidenceFoundationWorld, evidence_identity_signature, evidence_signature, record_payload
from app.generators.forecasts.generator import ForecastGenerator
from app.generators.forecasts.validation import ForecastValidator
from app.generators.forecasts.world import ForecastWorld, forecast_signature
from app.generators.procurement.config import ProcurementGenerationConfig
from app.generators.scenarios.config import ScenarioGenerationConfig
from app.models.platform import DatasetVersion
from app.models.platform.evidence_foundation import EVIDENCE_MODELS
from app.models.platform.forecasts import FORECAST_MODELS, WeeklyForecastSnapshot
from app.services.evidence_foundation_generation import EvidenceFoundationGenerationService


class ForecastGenerationError(RuntimeError):
    pass


@dataclass
class ForecastResult:
    dataset_version_id: object
    snapshot_date: object
    forecast_signature: str
    forecast_content_hash: str
    world: ForecastWorld
    reused: bool
    validation_status: str = 'PASS'


class ForecastGenerationService:
    def __init__(self, session, generator=None, validator=None):
        self.session = session
        self.generator = generator or ForecastGenerator()
        self.validator = validator or ForecastValidator()

    def generate(self, dataset_id, config, *, evidence_config=None, procurement_config=None, scenario_config=None):
        ec = evidence_config or EvidenceFoundationConfig()
        pc = procurement_config or ProcurementGenerationConfig.demo()
        sc = scenario_config or ScenarioGenerationConfig.demo()
        with self.session.begin():
            dataset = self.session.scalar(select(DatasetVersion).where(DatasetVersion.dataset_version_id == dataset_id).with_for_update())
            if dataset is None or dataset.status != 'GENERATING':
                raise ForecastGenerationError('DATASET_NOT_GENERATING')
            foundation = EvidenceFoundationGenerationService(self.session)
            master, procurement, scenario, master_hash, scenario_hash = foundation._prerequisites(dataset, pc, sc)
            args = (dataset.generation_signature, master_hash, procurement.procurement_facts_hash(), scenario_hash, sc, ec)
            evidence_sig, identity_sig = evidence_signature(*args), evidence_identity_signature(*args)
            evidence = EvidenceFoundationWorld(**{
                m.__tablename__: list(self.session.scalars(select(m).where(m.dataset_version_id == dataset_id)))
                for m in EVIDENCE_MODELS
            })
            if not all(evidence.counts().values()):
                raise ForecastGenerationError('INCOMPLETE_EVIDENCE_FOUNDATION')
            expected = foundation.generator.generate(dataset_id, dataset.snapshot_date, evidence_sig, ec, sc, master, procurement, scenario, identity_signature=identity_sig)
            evidence_hash = evidence.content_hash(evidence_sig)
            if evidence_hash != expected.content_hash(evidence_sig):
                raise ForecastGenerationError('INCOMPLETE_EVIDENCE_FOUNDATION')
            del expected
            foundation.validator.validate(evidence, master, procurement, scenario, dataset_id, dataset.snapshot_date, ec, sc)
            signature = forecast_signature(dataset.generation_signature, evidence_hash, config)
            expected_world = self.generator.generate(dataset_id, dataset.generation_signature, dataset.snapshot_date, signature, config, master, evidence)
            self.validator.validate(expected_world, master, procurement, scenario, evidence, dataset_id, dataset.generation_signature, dataset.snapshot_date, config, sc)
            expected_hash = expected_world.content_hash(signature)
            counts = {m.__tablename__: self.session.scalar(select(func.count()).select_from(m).where(m.dataset_version_id == dataset_id)) for m in FORECAST_MODELS}
            reused = any(counts.values())
            if reused:
                snapshot_ids = set(self.session.scalars(select(WeeklyForecastSnapshot.weekly_forecast_snapshot_id).where(WeeklyForecastSnapshot.dataset_version_id == dataset_id)))
                if snapshot_ids and snapshot_ids != {r.weekly_forecast_snapshot_id for r in expected_world.weekly_forecast_snapshots}:
                    raise ForecastGenerationError('FORECAST_CONFIG_CONFLICT')
                if counts != expected_world.counts():
                    raise ForecastGenerationError('INCOMPLETE_FORECAST_WORLD')
                actual = ForecastWorld(**{m.__tablename__: list(self.session.scalars(select(m).where(m.dataset_version_id == dataset_id))) for m in FORECAST_MODELS})
                if actual.content_hash(signature) != expected_hash:
                    raise ForecastGenerationError('FORECAST_CONFIG_CONFLICT')
                self.validator.validate(actual, master, procurement, scenario, evidence, dataset_id, dataset.generation_signature, dataset.snapshot_date, config, sc)
                world = actual
            else:
                for model in FORECAST_MODELS:
                    rows = getattr(expected_world, model.__tablename__)
                    for offset in range(0, len(rows), 2000):
                        self.session.execute(insert(model), [record_payload(r) for r in rows[offset:offset + 2000]])
                world = expected_world
            return ForecastResult(dataset_id, dataset.snapshot_date, signature, expected_hash, world, reused)
