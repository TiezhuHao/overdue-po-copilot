from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.generators.config import GenerationConfig


CORE_SIGNATURE_FIELDS = {
    "random_seed",
    "snapshot_date",
    "generator_version",
    "schema_version",
}


def canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return canonicalize(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {str(key): canonicalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [canonicalize(item) for item in value]
    if isinstance(value, Decimal):
        normalized = value.normalize()
        if normalized == 0:
            return "0"
        return format(normalized, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, float):
        return canonicalize(Decimal(str(value)))
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        canonicalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def generation_config_payload(config: GenerationConfig) -> dict[str, Any]:
    return config.model_dump(mode="python", exclude=CORE_SIGNATURE_FIELDS)


def generation_signature(config: GenerationConfig) -> str:
    payload = {
        "random_seed": config.random_seed,
        "snapshot_date": config.snapshot_date,
        "generator_version": config.generator_version,
        "schema_version": config.schema_version,
        "generation_config": generation_config_payload(config),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()

