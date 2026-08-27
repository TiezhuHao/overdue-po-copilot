from dataclasses import dataclass, field
from hashlib import sha256

from app.generators.evidence_foundation.world import record_payload
from app.generators.signature import canonical_json, content_hash
from app.models.platform.forecasts import FORECAST_MODELS


@dataclass
class ForecastWorld:
    forecast_versions: list = field(default_factory=list)
    monthly_forecasts: list = field(default_factory=list)
    material_project_shipments: list = field(default_factory=list)
    weekly_forecast_snapshots: list = field(default_factory=list)
    weekly_project_forecasts: list = field(default_factory=list)
    weekly_forecasts: list = field(default_factory=list)

    def counts(self):
        return {model.__tablename__: len(getattr(self, model.__tablename__)) for model in FORECAST_MODELS}

    def content_hash(self, signature):
        digest = sha256(signature.encode())
        for model in FORECAST_MODELS:
            digest.update(model.__tablename__.encode())
            keys = [c.key for c in model.__table__.primary_key]
            for row in sorted(getattr(self, model.__tablename__), key=lambda r: tuple(str(getattr(r, k)) for k in keys)):
                digest.update(canonical_json(record_payload(row)).encode())
                digest.update(b'\n')
        return digest.hexdigest()


def forecast_signature(dataset_signature, evidence_hash, config):
    return content_hash({'dataset': dataset_signature, 'evidence': evidence_hash, 'config': config})
