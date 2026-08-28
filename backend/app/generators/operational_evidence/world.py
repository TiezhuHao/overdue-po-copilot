from dataclasses import dataclass,field
from hashlib import sha256
from app.generators.signature import canonical_json
from app.models.platform.operational import OPERATIONAL_MODELS
from app.generators.evidence_foundation.world import record_payload
@dataclass
class OperationalEvidenceWorld:
    inventory_snapshots:list=field(default_factory=list); inventory_age_buckets:list=field(default_factory=list)
    supply_demand_snapshots:list=field(default_factory=list); supply_demand_components:list=field(default_factory=list)
    stockpile_versions:list=field(default_factory=list); stockpile_records:list=field(default_factory=list)
    stockpile_forecasts:list=field(default_factory=list); stockpile_balance_projections:list=field(default_factory=list)
    stockpile_inventory_age_buckets:list=field(default_factory=list)
    def counts(self): return {m.__tablename__:len(getattr(self,m.__tablename__)) for m in OPERATIONAL_MODELS}
    def content_hash(self, signature):
        h=sha256(signature.encode())
        for m in OPERATIONAL_MODELS:
            h.update(m.__tablename__.encode())
            for r in sorted(getattr(self,m.__tablename__),key=lambda x:tuple(str(getattr(x,c.key)) for c in m.__table__.primary_key)):
                h.update(canonical_json(record_payload(r)).encode()); h.update(b'\n')
        return h.hexdigest()
