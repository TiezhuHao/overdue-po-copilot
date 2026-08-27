from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ForecastGenerationConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    seed: int = 20260830
    generator_version: Literal['5B.1.0'] = '5B.1.0'
    schema_version: Literal['009'] = '009'
    version_frequency_days: Literal[7] = 7
    after_versions_default: int = Field(default=3, ge=2, le=5)
    after_versions_min: Literal[2] = 2
    after_versions_max: Literal[5] = 5
    monthly_horizon_months: Literal[7] = 7
    # Overlap facts support fixed seven-month comparisons across rolling views.
    comparison_lookback_months: Literal[2] = 2
    comparison_forward_months: Literal[1] = 1
    weekly_horizon_weeks: Literal[13] = 13
    revision_probability: Decimal = Field(default=Decimal('0.12'), ge=0, le=1)
    invalid_version_fixture_rate: Decimal = Field(default=Decimal('0.07'), ge=0, le=1)
    rounding_scale: Literal[4] = 4
    shipment_realization_ratio: Decimal = Field(default=Decimal('0.8'), ge=0, le=1)
    forecast_source: Literal['SYNTHETIC_PLANNING'] = 'SYNTHETIC_PLANNING'
