from collections import defaultdict
from dataclasses import dataclass, field
from hashlib import sha256

from app.generators.signature import canonical_json, content_hash
from app.models.platform.evidence_foundation import EVIDENCE_MODELS


def record_payload(row):
    return {column.key: getattr(row, column.key) for column in row.__table__.columns if column.key != "created_at"}


@dataclass
class EvidenceFoundationWorld:
    project_lifecycle_history: list = field(default_factory=list)
    product_configs: list = field(default_factory=list)
    product_config_materials: list = field(default_factory=list)
    demand_signals: list = field(default_factory=list)
    demand_signal_points: list = field(default_factory=list)
    demand_signal_revisions: list = field(default_factory=list)

    COLLECTION_NAMES = tuple(model.__tablename__ for model in EVIDENCE_MODELS)

    def counts(self):
        return {name: len(getattr(self, name)) for name in self.COLLECTION_NAMES}

    def content_hash(self, signature):
        # Stream hashes rather than constructing a second large JSON point world.
        digest = sha256(signature.encode())
        for model in EVIDENCE_MODELS:
            digest.update(model.__tablename__.encode())
            keys = [column.key for column in model.__table__.primary_key]
            for row in sorted(getattr(self, model.__tablename__), key=lambda item: tuple(str(getattr(item, key)) for key in keys)):
                digest.update(canonical_json(record_payload(row)).encode())
                digest.update(b"\n")
        return digest.hexdigest()


def evidence_signature(dataset_signature, master_hash, procurement_hash, scenario_hash, scenario_config, evidence_config):
    return content_hash({
        "dataset": dataset_signature, "master": master_hash, "procurement": procurement_hash,
        "scenario": scenario_hash, "scenario_config": scenario_config, "evidence_config": evidence_config,
    })


class DemandObservationIndex:
    """Quantity-only as-of projection, with no reference to evaluation or its labels."""

    def __init__(self, world):
        self.initial = defaultdict(dict)
        self.revisions = defaultdict(list)
        self.starts = {row.demand_signal_id: row.observed_from for row in world.demand_signals}
        for row in world.demand_signal_points:
            self.initial[row.demand_signal_id][row.demand_date] = row.demand_qty
        for row in world.demand_signal_revisions:
            self.revisions[row.demand_signal_id].append(row)
        for rows in self.revisions.values():
            rows.sort(key=lambda row: (row.observed_on, row.demand_date))

    def observe(self, signal_id, as_of):
        if as_of < self.starts[signal_id]:
            raise ValueError("DEMAND_OBSERVATION_OUTSIDE_HISTORY")
        result = dict(self.initial[signal_id])
        for row in self.revisions[signal_id]:
            if row.observed_on > as_of:
                break
            result[row.demand_date] = row.demand_qty
        return result
