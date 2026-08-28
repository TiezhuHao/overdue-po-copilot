"""Generator-only atomic operational stage; upstream worlds are read-only."""
from dataclasses import dataclass
from sqlalchemy import func, insert, select

from app.generators.evidence_foundation.config import EvidenceFoundationConfig
from app.generators.evidence_foundation.world import EvidenceFoundationWorld, evidence_identity_signature, evidence_signature, record_payload
from app.generators.forecasts.config import ForecastGenerationConfig
from app.generators.forecasts.generator import ForecastGenerator
from app.generators.forecasts.validation import ForecastValidator
from app.generators.forecasts.world import ForecastWorld, forecast_signature
from app.generators.operational_evidence.config import OperationalEvidenceConfig
from app.generators.operational_evidence.generator import OperationalEvidenceGenerator
from app.generators.operational_evidence.validation import OperationalEvidenceValidator
from app.generators.operational_evidence.world import OperationalEvidenceWorld
from app.generators.procurement.config import ProcurementGenerationConfig
from app.generators.scenarios.config import ScenarioGenerationConfig
from app.generators.signature import content_hash
from app.models.platform import DatasetVersion
from app.models.platform.evidence_foundation import EVIDENCE_MODELS
from app.models.platform.forecasts import FORECAST_MODELS
from app.models.platform.operational import OPERATIONAL_MODELS, InventorySnapshot
from app.services.evidence_foundation_generation import EvidenceFoundationGenerationService, EvidenceFoundationError


class OperationalEvidenceError(RuntimeError):
    pass


@dataclass
class OperationalEvidenceResult:
    dataset_version_id: object
    operational_content_hash: str
    world: OperationalEvidenceWorld
    reused: bool
    validation_summary: dict
    validation_status: str = 'PASS'


class OperationalEvidenceGenerationService:
    def __init__(self, session, generator=None, validator=None):
        self.session = session
        self.generator = generator or OperationalEvidenceGenerator()
        self.validator = validator or OperationalEvidenceValidator()

    def _load(self, models, world_type, dataset_id):
        return world_type(**{m.__tablename__: list(self.session.scalars(select(m).where(m.dataset_version_id == dataset_id)))
                             for m in models})

    def _prerequisites(self, dataset, pc, sc, ec, fc):
        foundation = EvidenceFoundationGenerationService(self.session)
        try:
            master, procurement, scenario, master_hash, scenario_hash = foundation._prerequisites(dataset, pc, sc)
        except EvidenceFoundationError as exc:
            raise OperationalEvidenceError(str(exc).split(':')[0]) from None
        did, snapshot = dataset.dataset_version_id, dataset.snapshot_date
        args = (dataset.generation_signature, master_hash, procurement.procurement_facts_hash(), scenario_hash, sc, ec)
        es, identity = evidence_signature(*args), evidence_identity_signature(*args)
        evidence = self._load(EVIDENCE_MODELS, EvidenceFoundationWorld, did)
        if not all(evidence.counts().values()):
            raise OperationalEvidenceError('INCOMPLETE_EVIDENCE_FOUNDATION')
        expected = foundation.generator.generate(did, snapshot, es, ec, sc, master, procurement, scenario, identity_signature=identity)
        evidence_hash = evidence.content_hash(es)
        if evidence_hash != expected.content_hash(es):
            raise OperationalEvidenceError('INCOMPLETE_EVIDENCE_FOUNDATION')
        del expected
        foundation.validator.validate(evidence, master, procurement, scenario, did, snapshot, ec, sc)
        forecast = self._load(FORECAST_MODELS, ForecastWorld, did)
        if not all(forecast.counts().values()):
            raise OperationalEvidenceError('INCOMPLETE_FORECAST_WORLD')
        fs = forecast_signature(dataset.generation_signature, evidence_hash, fc)
        expected = ForecastGenerator().generate(did, dataset.generation_signature, snapshot, fs, fc, master, evidence)
        forecast_hash = forecast.content_hash(fs)
        if forecast_hash != expected.content_hash(fs):
            raise OperationalEvidenceError('INCOMPLETE_FORECAST_WORLD')
        del expected
        ForecastValidator().validate(forecast, master, procurement, scenario, evidence, did,
                                     dataset.generation_signature, snapshot, fc, sc)
        hashes = {'dataset': dataset.generation_signature, 'master': master_hash,
                  'procurement': procurement.procurement_facts_hash(), 'scenario': scenario_hash,
                  'evidence': evidence_hash, 'forecast': forecast_hash}
        return master, procurement, scenario, evidence, forecast, hashes

    def generate(self, dataset_id, config=None, *, procurement_config=None, scenario_config=None,
                 evidence_config=None, forecast_config=None):
        config = config or OperationalEvidenceConfig()
        pc, sc = procurement_config or ProcurementGenerationConfig.demo(), scenario_config or ScenarioGenerationConfig.demo()
        ec, fc = evidence_config or EvidenceFoundationConfig(), forecast_config or ForecastGenerationConfig()
        with self.session.begin():
            dataset = self.session.scalar(select(DatasetVersion).where(
                DatasetVersion.dataset_version_id == dataset_id).with_for_update())
            if dataset is None or dataset.status != 'GENERATING':
                raise OperationalEvidenceError('DATASET_NOT_GENERATING')
            master, procurement, scenario, evidence, forecast, hashes = self._prerequisites(dataset, pc, sc, ec, fc)
            signature = content_hash({'upstream': hashes, 'config': config})
            expected = self.generator.generate(dataset_id, dataset.snapshot_date, signature, config,
                                               master, procurement, scenario, evidence, forecast)
            args = (master, procurement, scenario, evidence, forecast, dataset_id, dataset.snapshot_date, signature, config, sc)
            validation = self.validator.validate(expected, *args)
            expected_hash = expected.content_hash(signature)
            counts = {m.__tablename__: self.session.scalar(select(func.count()).select_from(m).where(m.dataset_version_id == dataset_id))
                      for m in OPERATIONAL_MODELS}
            reused = any(counts.values())
            if reused:
                stored_ids = set(self.session.scalars(select(InventorySnapshot.inventory_snapshot_id).where(InventorySnapshot.dataset_version_id == dataset_id)))
                expected_ids = {r.inventory_snapshot_id for r in expected.inventory_snapshots}
                if stored_ids and not stored_ids <= expected_ids:
                    raise OperationalEvidenceError('OPERATIONAL_CONFIG_CONFLICT')
                if counts != expected.counts():
                    raise OperationalEvidenceError('INCOMPLETE_OPERATIONAL_EVIDENCE')
                actual = self._load(OPERATIONAL_MODELS, OperationalEvidenceWorld, dataset_id)
                if {r.inventory_snapshot_id for r in actual.inventory_snapshots} != {r.inventory_snapshot_id for r in expected.inventory_snapshots}:
                    raise OperationalEvidenceError('OPERATIONAL_CONFIG_CONFLICT')
                self.validator.validate(actual, *args)
                if actual.content_hash(signature) != expected_hash:
                    raise OperationalEvidenceError('OPERATIONAL_CONTENT_MISMATCH')
                world = actual
            else:
                for model in OPERATIONAL_MODELS:
                    rows = getattr(expected, model.__tablename__)
                    for offset in range(0, len(rows), 2000):
                        self.session.execute(insert(model), [record_payload(r) for r in rows[offset:offset + 2000]])
                world = expected
            return OperationalEvidenceResult(dataset_id, expected_hash, world, reused, validation)
