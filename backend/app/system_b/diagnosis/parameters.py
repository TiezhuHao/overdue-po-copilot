"""Explicit caller-supplied business parameters; no demo/enterprise defaults."""
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.system_b.models import CanonicalModel, Quantity

Ratio = Annotated[Quantity, Field(gt=0, le=1)]


class DemandChangeParameters(CanonicalModel):
    total_drop_ratio: Ratio
    later_shift_ratio: Ratio
    min_comparison_months: Annotated[int, Field(strict=True, ge=2, le=7)]
    post_version_count: Annotated[int, Field(strict=True, ge=2, le=5)]


class AfterSalesParameters(CanonicalModel):
    # Explicit thirteen-week project window; not a hidden normal-demand reference.
    max_average_weekly_qty: Annotated[Quantity, Field(gt=0)]
    min_nonzero_weeks: Annotated[int, Field(strict=True, ge=1, le=13)]
    min_consecutive_weeks: Annotated[int, Field(strict=True, ge=1, le=13)]


class BusinessDiagnosisPolicy(CanonicalModel):
    policy_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    demand_change: DemandChangeParameters | None = None
    after_sales: AfterSalesParameters | None = None
    valid_stockpile_tags: tuple[str, ...] | None = None

    @model_validator(mode="after")
    def validate_labels(self) -> Self:
        if not self.policy_id.strip() or not self.version.strip():
            raise ValueError("EMPTY_POLICY_IDENTITY")
        if self.valid_stockpile_tags is not None:
            if (not self.valid_stockpile_tags or any(not tag.strip() for tag in self.valid_stockpile_tags)
                    or len(set(self.valid_stockpile_tags)) != len(self.valid_stockpile_tags)):
                raise ValueError("INVALID_STOCKPILE_TAG_DEFINITIONS")
        return self
