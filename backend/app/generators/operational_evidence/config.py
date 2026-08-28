from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class OperationalEvidenceConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    seed: int = 20260831
    generator_version: Literal['5C.2.0'] = '5C.2.0'
    schema_version: Literal['010'] = '010'
    rounding_scale: Literal[4] = 4
    inventory_base_min: Decimal = Field(default=Decimal('0'), ge=0)
    inventory_base_max: Decimal = Field(default=Decimal('500'), ge=0)
    inventory_demand_cover_min: Decimal = Field(default=Decimal('0.05'), ge=0)
    inventory_demand_cover_max: Decimal = Field(default=Decimal('1.40'), ge=0)
    availability_min: Decimal = Field(default=Decimal('0.70'), ge=0, le=1)
    availability_max: Decimal = Field(default=Decimal('0.95'), ge=0, le=1)
    age_retention_min: Decimal = Field(default=Decimal('0.60'), ge=0, le=1)
    age_retention_max: Decimal = Field(default=Decimal('0.90'), ge=0, le=1)
    in_transit_ratio: Decimal = Field(default=Decimal('0.20'), ge=0, le=1)
    work_order_days: int = Field(default=7, ge=1, le=14)
    plan_days: int = Field(default=14, ge=1, le=28)
    forecast_days: int = Field(default=7, ge=1, le=14)
    work_order_ratio: Decimal = Field(default=Decimal('0.85'), ge=0, le=2)
    plan_ratio: Decimal = Field(default=Decimal('0.75'), ge=0, le=2)
    forecast_ratio: Decimal = Field(default=Decimal('0.60'), ge=0, le=2)
    stockpile_version_frequency_days: int = Field(default=7, ge=1, le=31)
    stockpile_period_min: int = Field(default=1, ge=1, le=6)
    stockpile_period_max: int = Field(default=6, ge=1, le=6)
    stockpile_achievement_min: Decimal = Field(default=Decimal('0.60'), ge=0)
    stockpile_achievement_max: Decimal = Field(default=Decimal('1.20'), ge=0)
    stockpile_inbound_ratio: Decimal = Field(default=Decimal('0.10'), ge=0, le=1)

    @model_validator(mode='after')
    def ranges(self):
        for prefix in ('inventory_base', 'inventory_demand_cover', 'availability', 'age_retention',
                       'stockpile_period', 'stockpile_achievement'):
            if getattr(self, prefix + '_min') > getattr(self, prefix + '_max'):
                raise ValueError(prefix + '_RANGE_REVERSED')
        return self


AGE_THRESHOLDS = (30, 60, 90, 120, 150, 180, 270, 360, 365, 540)
SUPPLY_TYPES = frozenset({'ON_HAND_AVAILABLE', 'OPEN_PO', 'IN_TRANSIT', 'OTHER_CONFIRMED_SUPPLY'})
