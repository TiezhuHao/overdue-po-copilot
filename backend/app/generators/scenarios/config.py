from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.generators.scenarios.mappings import MASS_PATTERNS


class ScenarioGenerationConfig(BaseModel):
    scenario_seed: int = 20260828
    generator_version: str = "4.0.0"
    schema_version: str = "007"
    mass_pattern_weights: dict[str, Decimal] = Field(
        default_factory=lambda: {
            "DEMAND_REDUCTION": Decimal("0.15"),
            "DEMAND_DELAY": Decimal("0.12"),
            "DEMAND_MIXED": Decimal("0.10"),
            "CUSTOMER_SIDE_PROJECT_OBSOLESCENCE": Decimal("0.15"),
            "AFTER_SALES": Decimal("0.15"),
            "STOCKPILE": Decimal("0.18"),
            "INTERNAL_SIDE_PROJECT_OBSOLESCENCE": Decimal("0.15"),
        }
    )
    reference_causal_mismatch_min_ratio: Decimal = Decimal("0.15")
    require_all_patterns: bool = True
    require_after_sales_stockpile_both: bool = True
    require_customer_demand_change_coverage: bool = True

    comparison_months: int = 7
    reduction_total_drop_ratio: Decimal = Decimal("0.35")
    delay_near_term_months: int = 3
    delay_near_term_drop_ratio: Decimal = Decimal("0.30")
    delay_total_retention_lower: Decimal = Decimal("0.85")
    delay_total_retention_upper: Decimal = Decimal("1.15")
    delay_shift_share_min: Decimal = Decimal("0.30")
    mixed_total_drop_ratio: Decimal = Decimal("0.20")
    mixed_shift_share_min: Decimal = Decimal("0.20")
    after_sales_level_ratio_min: Decimal = Decimal("0.05")
    after_sales_level_ratio_max: Decimal = Decimal("0.20")
    after_sales_min_nonzero_weeks: int = 8
    after_sales_min_nonzero_months: int = 4
    forecast_rounding_tolerance: Decimal = Decimal("0.01")

    @model_validator(mode="after")
    def validate_config(self) -> Self:
        if set(self.mass_pattern_weights) != set(MASS_PATTERNS):
            raise ValueError("mass_pattern_weights must define exactly seven patterns")
        if any(weight < 0 for weight in self.mass_pattern_weights.values()):
            raise ValueError("mass_pattern_weights must be nonnegative")
        if sum(self.mass_pattern_weights.values()) != Decimal("1"):
            raise ValueError("mass_pattern_weights must sum to 1")
        if self.delay_total_retention_lower > self.delay_total_retention_upper:
            raise ValueError("delay retention lower bound cannot exceed upper bound")
        if self.after_sales_level_ratio_min > self.after_sales_level_ratio_max:
            raise ValueError("after-sales level lower bound cannot exceed upper bound")
        return self

    @classmethod
    def demo(cls, **overrides: object) -> Self:
        return cls(**overrides)

    @classmethod
    def small_test(cls, **overrides: object) -> Self:
        values: dict[str, object] = {
            "scenario_seed": 654,
            "require_all_patterns": False,
            "require_after_sales_stockpile_both": False,
            "require_customer_demand_change_coverage": False,
            "reference_causal_mismatch_min_ratio": Decimal("0"),
        }
        values.update(overrides)
        return cls(**values)
