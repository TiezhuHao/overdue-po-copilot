from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceFoundationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_seed: int = 20260829
    generator_version: Literal["5A.1.0"] = "5A.1.0"
    schema_version: Literal["008"] = "008"
    revision_timing_version: Literal["PERSISTENT_1"] = "PERSISTENT_1"
    history_months_before_anchor: int = Field(default=2, ge=2)
    future_months: int = Field(default=8, ge=8)
    configs_per_project: int = Field(default=2, ge=1, le=5)
    reference_daily_qty_min: int = Field(default=40, ge=1)
    reference_daily_qty_max: int = Field(default=120, ge=1)
    daily_noise_ratio: Decimal = Field(default=Decimal("0.02"), ge=0, le=Decimal("0.05"))
    reduction_drop_ratio: Decimal = Field(default=Decimal("0.55"), gt=0, lt=1)
    delay_near_shift_ratio: Decimal = Field(default=Decimal("0.80"), gt=0, lt=1)
    mixed_drop_ratio: Decimal = Field(default=Decimal("0.25"), gt=0, lt=1)
    mixed_near_shift_ratio: Decimal = Field(default=Decimal("0.30"), gt=0, lt=1)
    planning_cycle_retention: Decimal = Field(default=Decimal("0.90"), gt=0, le=1)

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if self.reference_daily_qty_min > self.reference_daily_qty_max:
            raise ValueError("reference daily quantity bounds are reversed")
        # Preserve legacy identity inputs, but never silently accept inactive
        # pulse-amplitude overrides under the persistent-state implementation.
        for name in ('reduction_drop_ratio', 'delay_near_shift_ratio', 'mixed_drop_ratio',
                     'mixed_near_shift_ratio', 'planning_cycle_retention'):
            if getattr(self, name) != type(self).model_fields[name].default:
                raise ValueError('legacy pulse settings cannot override persistent revision states')
        return self
