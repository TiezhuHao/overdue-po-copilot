from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from app.models import Base
from app.models.platform.material import Material
from app.models.platform.project import Project


EXPECTED_TABLES = {
    "platform.dataset_versions",
    "platform.organizations",
    "platform.employees",
    "platform.materials",
    "platform.projects",
    "platform.customers",
    "platform.suppliers",
    "platform.material_projects",
    "platform.material_mpm_assignments",
    "platform.employee_role_assignments",
    "platform.material_supplier_assignments",
    "platform.project_customers",
    "platform.material_responsibility_assignments",
    "platform.po_headers",
    "platform.po_lines",
    "platform.po_line_schedules",
    "evaluation.scenario_truth",
    "platform.project_lifecycle_history",
    "platform.product_configs",
    "platform.product_config_materials",
    "platform.demand_signals",
    "platform.demand_signal_points",
    "platform.demand_signal_revisions",
    "platform.forecast_versions",
    "platform.monthly_forecasts",
    "platform.material_project_shipments",
    "platform.weekly_forecast_snapshots",
    "platform.weekly_project_forecasts",
    "platform.weekly_forecasts",
    "platform.inventory_snapshots",
    "platform.inventory_age_buckets",
    "platform.supply_demand_snapshots",
    "platform.supply_demand_components",
    "platform.stockpile_versions",
    "platform.stockpile_records",
    "platform.stockpile_forecasts",
    "platform.stockpile_balance_projections",
    "platform.stockpile_inventory_age_buckets",
}


def test_metadata_contains_only_authorized_tables_through_phase_5c() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_material_primary_organization_fk_is_dataset_scoped() -> None:
    table = Material.__table__
    assert not table.c.primary_inventory_organization_id.nullable
    fk_column_sets = {
        tuple(element.parent.name for element in constraint.elements)
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    assert ("dataset_version_id", "primary_inventory_organization_id") in fk_column_sets


def test_project_name_is_not_unique_but_code_is_dataset_unique() -> None:
    table = Project.__table__
    unique_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("dataset_version_id", "project_code") in unique_sets
    assert all("project_name" not in columns for columns in unique_sets)


def test_project_to_mpm_table_does_not_exist() -> None:
    assert "platform.project_mpm_assignments" not in Base.metadata.tables
