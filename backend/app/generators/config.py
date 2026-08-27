from datetime import date
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, model_validator


class GenerationConfig(BaseModel):
    random_seed: int = 20260826
    snapshot_date: date = date(2026, 8, 26)
    generator_version: str = "2.0.0"
    schema_version: str = "005"

    business_entity_count: int = Field(default=1, ge=1, le=3)
    business_unit_count: int = Field(default=3, ge=1)
    planning_department_count: int = Field(default=4, ge=1)
    inventory_organization_count: int = Field(default=5, ge=2)
    department_count: int = Field(default=5, ge=1)

    employee_count: int = Field(default=40, ge=8)
    material_count: int = Field(default=60, ge=1)
    project_count: int = Field(default=30, ge=1)
    customer_count: int = Field(default=12, ge=1)
    supplier_count: int = Field(default=15, ge=1)

    min_projects_per_material: int = Field(default=1, ge=1)
    max_projects_per_material: int = Field(default=4, ge=1)
    trial_inventory_org_ratio: Decimal = Field(
        default=Decimal("0.20"), gt=Decimal("0"), lt=Decimal("1")
    )
    same_project_name_fixture_enabled: bool = True
    generation_options: dict[str, bool | int | str | Decimal] = Field(
        default_factory=lambda: {
            "historical_mpm_switches": True,
            "alternate_supplier_ratio_percent": 35,
        }
    )

    @model_validator(mode="after")
    def validate_world_shape(self) -> Self:
        if self.min_projects_per_material > self.max_projects_per_material:
            raise ValueError("min_projects_per_material cannot exceed max_projects_per_material")
        if self.max_projects_per_material > self.project_count:
            raise ValueError("max_projects_per_material cannot exceed project_count")
        if self.project_count > self.material_count * self.max_projects_per_material:
            raise ValueError("project capacity is too small to keep every project connected")
        if self.material_count < self.supplier_count:
            raise ValueError("material_count must be at least supplier_count")
        if self.project_count < self.customer_count:
            raise ValueError("project_count must be at least customer_count")
        if self.same_project_name_fixture_enabled and self.project_count < 2:
            raise ValueError("same-name project fixture requires at least two projects")
        return self

    @property
    def organization_count(self) -> int:
        return (
            self.business_entity_count
            + self.business_unit_count
            + self.planning_department_count
            + self.inventory_organization_count
            + self.department_count
        )

    @classmethod
    def demo(cls, **overrides: object) -> Self:
        return cls(**overrides)

    @classmethod
    def small_test(cls, **overrides: object) -> Self:
        values: dict[str, object] = {
            "random_seed": 123,
            "snapshot_date": date(2026, 8, 26),
            "business_entity_count": 1,
            "business_unit_count": 2,
            "planning_department_count": 2,
            "inventory_organization_count": 3,
            "department_count": 2,
            "employee_count": 10,
            "material_count": 8,
            "project_count": 6,
            "customer_count": 4,
            "supplier_count": 4,
            "min_projects_per_material": 1,
            "max_projects_per_material": 3,
            "trial_inventory_org_ratio": Decimal("0.34"),
        }
        values.update(overrides)
        return cls(**values)

