from typing import Self

from pydantic import BaseModel, Field, model_validator


class ProcurementGenerationConfig(BaseModel):
    random_seed: int = 20260827
    generator_version: str = "3.0.0"
    schema_version: str = "006"
    po_header_count: int = Field(default=100, ge=1)
    min_lines_per_po: int = Field(default=1, ge=1)
    max_lines_per_po: int = Field(default=3, ge=1)
    overdue_candidate_ratio: float = Field(default=0.55, ge=0, le=1)
    trial_po_ratio: float = Field(default=0.20, gt=0, lt=1)
    open_po_ratio: float = Field(default=0.70, ge=0, le=1)
    partial_receipt_ratio: float = Field(default=0.55, ge=0, le=1)
    min_quantity: int = Field(default=10, ge=1)
    max_quantity: int = Field(default=1000, ge=1)
    generation_options: dict[str, int | bool | str] = Field(
        default_factory=lambda: {"max_extra_overdue_days": 180}
    )

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if self.min_lines_per_po > self.max_lines_per_po:
            raise ValueError("min_lines_per_po cannot exceed max_lines_per_po")
        if self.min_quantity > self.max_quantity:
            raise ValueError("min_quantity cannot exceed max_quantity")
        return self

    @classmethod
    def demo(cls, **overrides: object) -> Self:
        return cls(**overrides)

    @classmethod
    def small_test(cls, **overrides: object) -> Self:
        values: dict[str, object] = {
            "random_seed": 321,
            "po_header_count": 8,
            "min_lines_per_po": 1,
            "max_lines_per_po": 2,
            "min_quantity": 10,
            "max_quantity": 100,
        }
        values.update(overrides)
        return cls(**values)
