"""Explicit, generator-only correction of an audited GENERATING evidence world."""

from sqlalchemy import delete, insert, inspect, select, update

from app.generators.evidence_foundation.config import EvidenceFoundationConfig
from app.generators.evidence_foundation.world import EvidenceFoundationWorld, evidence_identity_signature, evidence_signature, record_payload
from app.generators.procurement.config import ProcurementGenerationConfig
from app.generators.scenarios.config import ScenarioGenerationConfig
from app.models.platform import DatasetVersion
from app.models.platform.evidence_foundation import EVIDENCE_MODELS, DemandSignal, DemandSignalPoint, DemandSignalRevision
from app.services.evidence_foundation_generation import EvidenceFoundationError, EvidenceFoundationGenerationService, EvidenceFoundationResult


class EvidenceTimingCorrectionService(EvidenceFoundationGenerationService):
    def correct(self, dataset_id, expected_old_hash, *, config=None, procurement_config=None, scenario_config=None):
        config = config or EvidenceFoundationConfig()
        pc = procurement_config or ProcurementGenerationConfig.demo()
        sc = scenario_config or ScenarioGenerationConfig.demo()
        with self.session.begin():
            dataset = self.session.scalar(select(DatasetVersion).where(DatasetVersion.dataset_version_id == dataset_id).with_for_update())
            if dataset is None or dataset.version_name != 'demo-master-v1':
                raise EvidenceFoundationError('CORRECTION_TARGET_NOT_DEMO')
            if dataset.status != 'GENERATING':
                raise EvidenceFoundationError('DATASET_NOT_GENERATING')
            if {'forecast_versions', 'stockpile_versions'} & set(inspect(self.session.connection()).get_table_names(schema='platform')):
                raise EvidenceFoundationError('CORRECTION_DOWNSTREAM_SCHEMA_EXISTS')
            master, procurement, scenario, master_hash, scenario_hash = self._prerequisites(dataset, pc, sc)
            args = (dataset.generation_signature, master_hash, procurement.procurement_facts_hash(), scenario_hash, sc, config)
            signature = evidence_signature(*args)
            identity = evidence_identity_signature(*args)
            stored = EvidenceFoundationWorld(**{
                model.__tablename__: list(self.session.scalars(select(model).where(model.dataset_version_id == dataset_id)))
                for model in EVIDENCE_MODELS
            })
            corrected = self.generator.generate(dataset_id, dataset.snapshot_date, signature, config, sc, master, procurement, scenario, identity_signature=identity)
            self.validator.validate(corrected, master, procurement, scenario, dataset_id, dataset.snapshot_date, config, sc)
            new_hash = corrected.content_hash(signature)
            if stored.content_hash(signature) == new_hash:
                return EvidenceFoundationResult(dataset_id, dataset.snapshot_date, signature, new_hash, stored, True)
            if stored.content_hash(identity) != expected_old_hash:
                raise EvidenceFoundationError('CORRECTION_OLD_HASH_MISMATCH')

            def keyed(world, model):
                keys = [col.key for col in model.__table__.primary_key]
                return {tuple(getattr(row, key) for key in keys): record_payload(row)
                        for row in getattr(world, model.__tablename__)}

            # Lifecycle and configuration rows (including their IDs) are never written.
            for model in EVIDENCE_MODELS[:3]:
                if keyed(stored, model) != keyed(corrected, model):
                    raise EvidenceFoundationError('CORRECTION_STRUCTURAL_EVIDENCE_CHANGED')
            for model in (DemandSignal, DemandSignalPoint):
                if keyed(stored, model).keys() != keyed(corrected, model).keys():
                    raise EvidenceFoundationError('CORRECTION_DEMAND_IDENTITIES_CHANGED')
            old_points = {row.demand_signal_point_id: row.demand_qty for row in stored.demand_signal_points}
            changed_points = [{
                'dataset_version_id': dataset_id, 'demand_signal_point_id': row.demand_signal_point_id,
                'demand_qty': row.demand_qty,
            } for row in corrected.demand_signal_points if old_points[row.demand_signal_point_id] != row.demand_qty]
            self.session.execute(delete(DemandSignalRevision).where(DemandSignalRevision.dataset_version_id == dataset_id))
            for offset in range(0, len(changed_points), 2000):
                self.session.execute(update(DemandSignalPoint), changed_points[offset:offset + 2000])
            self.session.execute(update(DemandSignal), [{
                'dataset_version_id': dataset_id, 'demand_signal_id': row.demand_signal_id,
                'scenario_generation_key': row.scenario_generation_key,
            } for row in corrected.demand_signals])
            for offset in range(0, len(corrected.demand_signal_revisions), 2000):
                self.session.execute(insert(DemandSignalRevision), [record_payload(row) for row in corrected.demand_signal_revisions[offset:offset + 2000]])
            self.session.expire_all()
            actual = EvidenceFoundationWorld(**{
                model.__tablename__: list(self.session.scalars(select(model).where(model.dataset_version_id == dataset_id)))
                for model in EVIDENCE_MODELS
            })
            if actual.content_hash(signature) != new_hash:
                raise EvidenceFoundationError('CORRECTION_ROUNDTRIP_HASH_MISMATCH')
            self.validator.validate(actual, master, procurement, scenario, dataset_id, dataset.snapshot_date, config, sc)
            after = self._prerequisites(dataset, pc, sc)
            if (after[3], after[4], after[1].procurement_facts_hash()) != (master_hash, scenario_hash, procurement.procurement_facts_hash()):
                raise EvidenceFoundationError('CORRECTION_UPSTREAM_CHANGED')
            return EvidenceFoundationResult(dataset_id, dataset.snapshot_date, signature, new_hash, actual, False)
