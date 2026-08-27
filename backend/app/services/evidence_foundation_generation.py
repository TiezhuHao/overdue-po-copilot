from dataclasses import dataclass
from random import Random

from sqlalchemy import func, insert, select

from app.generators.config import GenerationConfig
from app.generators.context import GenerationContext
from app.generators.evidence_foundation.config import EvidenceFoundationConfig
from app.generators.evidence_foundation.generator import EvidenceFoundationGenerator
from app.generators.evidence_foundation.validation import EvidenceFoundationValidator
from app.generators.evidence_foundation.world import EvidenceFoundationWorld, evidence_identity_signature, evidence_signature, record_payload
from app.generators.master_data.generator import MasterDataGenerator
from app.generators.procurement.config import ProcurementGenerationConfig
from app.generators.procurement.generator import ProcurementGenerator
from app.generators.procurement.signature import procurement_generation_signature
from app.generators.scenarios.config import ScenarioGenerationConfig
from app.generators.scenarios.planner import ScenarioPlanner
from app.generators.scenarios.signature import scenario_generation_signature
from app.generators.scenarios.validation import ScenarioWorldValidator
from app.generators.signature import generation_signature
from app.models.evaluation import ScenarioTruth
from app.models.platform import DatasetVersion
from app.models.platform.evidence_foundation import EVIDENCE_MODELS, DemandSignal
from app.services.scenario_generation import ScenarioGenerationService


class EvidenceFoundationError(RuntimeError):
    pass


@dataclass
class EvidenceFoundationResult:
    dataset_version_id: object
    snapshot_date: object
    evidence_foundation_signature: str
    evidence_foundation_content_hash: str
    world: EvidenceFoundationWorld
    reused: bool
    validation_status: str = "PASS"


class EvidenceFoundationGenerationService:
    def __init__(self, session, generator=None, validator=None):
        self.session = session
        self.generator = generator or EvidenceFoundationGenerator()
        self.validator = validator or EvidenceFoundationValidator()

    def _prerequisites(self, dataset, procurement_config, scenario_config):
        loader = ScenarioGenerationService(self.session)
        master = loader._load_master(dataset.dataset_version_id)
        try:
            master_config = GenerationConfig(
                **dataset.generation_config, random_seed=dataset.random_seed,
                snapshot_date=dataset.snapshot_date, generator_version=dataset.generator_version,
                schema_version=dataset.schema_version,
            )
            expected_master = MasterDataGenerator().generate(GenerationContext(
                dataset.dataset_version_id, dataset.generation_signature, master_config, Random(master_config.random_seed),
            ))
            master_hash = master.master_content_hash(dataset.generation_signature)
            if (generation_signature(master_config) != dataset.generation_signature or
                    master_hash != expected_master.master_content_hash(dataset.generation_signature)):
                raise ValueError("master mismatch")
        except (ValueError, KeyError, IndexError) as exc:
            raise EvidenceFoundationError("INCOMPLETE_MASTER_WORLD") from exc
        procurement = loader._load_procurement(dataset.dataset_version_id)
        procurement_signature = procurement_generation_signature(dataset.generation_signature, procurement_config)
        expected_procurement = ProcurementGenerator().generate(
            dataset.dataset_version_id, dataset.snapshot_date, procurement_signature, procurement_config, master,
        )
        if procurement.procurement_content_hash(procurement_signature) != expected_procurement.procurement_content_hash(procurement_signature):
            raise EvidenceFoundationError("INCOMPLETE_PROCUREMENT_WORLD: missing facts or configuration mismatch")
        truth_rows = list(self.session.scalars(select(ScenarioTruth).where(ScenarioTruth.dataset_version_id == dataset.dataset_version_id)))
        signature = scenario_generation_signature(dataset.generation_signature, procurement.procurement_facts_hash(), scenario_config)
        try:
            if not truth_rows:
                raise ValueError("scenario missing")
            scenario = loader._reconstruct_world(truth_rows, procurement)
            ScenarioWorldValidator().validate(scenario, master, procurement, dataset.dataset_version_id, dataset.snapshot_date, scenario_config)
            expected_scenario = ScenarioPlanner().plan(dataset.dataset_version_id, dataset.snapshot_date, signature, scenario_config, master, procurement)
            scenario_hash = scenario.scenario_content_hash(signature)
            if scenario_hash != expected_scenario.scenario_content_hash(signature):
                raise ValueError("scenario mismatch")
        except (ValueError, KeyError) as exc:
            raise EvidenceFoundationError("INCOMPLETE_SCENARIO_WORLD: missing facts or configuration mismatch") from exc
        return master, procurement, scenario, master_hash, scenario_hash

    def generate(self, dataset_id, config: EvidenceFoundationConfig, *, procurement_config=None, scenario_config=None):
        procurement_config = procurement_config or ProcurementGenerationConfig.demo()
        scenario_config = scenario_config or ScenarioGenerationConfig.demo()
        with self.session.begin():
            dataset = self.session.scalar(select(DatasetVersion).where(DatasetVersion.dataset_version_id == dataset_id).with_for_update())
            if dataset is None:
                raise EvidenceFoundationError("DATASET_NOT_FOUND")
            if dataset.status != "GENERATING":
                raise EvidenceFoundationError("DATASET_NOT_GENERATING")
            master, procurement, scenario, master_hash, scenario_hash = self._prerequisites(dataset, procurement_config, scenario_config)
            signature = evidence_signature(dataset.generation_signature, master_hash, procurement.procurement_facts_hash(), scenario_hash, scenario_config, config)
            identity_signature = evidence_identity_signature(dataset.generation_signature, master_hash, procurement.procurement_facts_hash(), scenario_hash, scenario_config, config)
            existing_counts = {
                model.__tablename__: self.session.scalar(select(func.count()).select_from(model).where(model.dataset_version_id == dataset_id))
                for model in EVIDENCE_MODELS
            }
            world = self.generator.generate(dataset_id, dataset.snapshot_date, signature, config, scenario_config, master, procurement, scenario, identity_signature=identity_signature)
            self.validator.validate(world, master, procurement, scenario, dataset_id, dataset.snapshot_date, config, scenario_config)
            expected_hash = world.content_hash(signature)
            reused = any(existing_counts.values())
            if reused:
                expected_keys = {(row.material_id, row.project_id): row.scenario_generation_key for row in world.demand_signals}
                existing_signals = self.session.scalars(select(DemandSignal).where(DemandSignal.dataset_version_id == dataset_id))
                if any(row.scenario_generation_key != expected_keys.get((row.material_id, row.project_id)) for row in existing_signals):
                    raise EvidenceFoundationError("EVIDENCE_CONFIG_CONFLICT")
                if existing_counts != world.counts():
                    raise EvidenceFoundationError("INCOMPLETE_EVIDENCE_FOUNDATION")
                del world
                world = EvidenceFoundationWorld(**{
                    model.__tablename__: list(self.session.scalars(select(model).where(model.dataset_version_id == dataset_id)))
                    for model in EVIDENCE_MODELS
                })
                self.validator.validate(world, master, procurement, scenario, dataset_id, dataset.snapshot_date, config, scenario_config)
                if world.content_hash(signature) != expected_hash:
                    raise EvidenceFoundationError("EVIDENCE_CONFIG_CONFLICT")
            else:
                for model in EVIDENCE_MODELS:
                    rows = getattr(world, model.__tablename__)
                    for offset in range(0, len(rows), 2000):
                        self.session.execute(insert(model), [record_payload(row) for row in rows[offset:offset + 2000]])
            return EvidenceFoundationResult(dataset_id, dataset.snapshot_date, signature, expected_hash, world, reused)
