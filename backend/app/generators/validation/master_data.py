from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from typing import Any

from app.generators.master_data.world import MasterWorld


class MasterWorldValidationError(ValueError):
    pass


def _active(row: Any, as_of: date) -> bool:
    return row.effective_from <= as_of and (
        row.effective_to is None or as_of < row.effective_to
    )


class MasterDataValidator:
    """Fail-fast validation of the Phase 2 in-memory enterprise world."""

    def validate(self, world: MasterWorld, dataset_version_id: Any, as_of: date) -> None:
        errors: list[str] = []

        for collection_name in world.COLLECTION_NAMES:
            rows = getattr(world, collection_name)
            if any(row.dataset_version_id != dataset_version_id for row in rows):
                errors.append(f"{collection_name} contains a cross-dataset row")
            ids = [
                getattr(row, column.key)
                for row in rows
                for column in row.__table__.primary_key.columns
                if column.key != "dataset_version_id"
            ]
            if len(ids) != len(set(ids)):
                errors.append(f"{collection_name} contains duplicate identifiers")

        organizations = {row.organization_id: row for row in world.organizations}
        employees = {row.employee_id: row for row in world.employees}
        materials = {row.material_id: row for row in world.materials}
        projects = {row.project_id: row for row in world.projects}
        customers = {row.customer_id: row for row in world.customers}
        suppliers = {row.supplier_id: row for row in world.suppliers}

        for name, rows, attribute in (
            ("organization", world.organizations, "organization_code"),
            ("employee", world.employees, "employee_code"),
            ("material", world.materials, "material_code"),
            ("project", world.projects, "project_code"),
            ("customer", world.customers, "customer_code"),
            ("supplier", world.suppliers, "supplier_code"),
        ):
            values = [getattr(row, attribute) for row in rows]
            if len(values) != len(set(values)):
                errors.append(f"duplicate {name} business code")

        valid_organization_types = {
            "BUSINESS_ENTITY",
            "BUSINESS_UNIT",
            "PLANNING_DEPARTMENT",
            "INVENTORY_ORG",
            "DEPARTMENT",
        }
        for organization in world.organizations:
            if organization.organization_type not in valid_organization_types:
                errors.append("invalid organization type")
            if organization.parent_organization_id is not None:
                if organization.parent_organization_id not in organizations:
                    errors.append("organization parent does not exist")
                if organization.parent_organization_id == organization.organization_id:
                    errors.append("organization cannot be its own parent")
            is_inventory = organization.organization_type == "INVENTORY_ORG"
            if is_inventory != (organization.inventory_organization_type is not None):
                errors.append("inventory organization type scope is invalid")

        for employee in world.employees:
            if employee.organization_id not in organizations:
                errors.append("employee organization does not exist")
            for related_id in (employee.manager_employee_id, employee.director_employee_id):
                if related_id is not None and related_id not in employees:
                    errors.append("employee hierarchy reference does not exist")
                if related_id == employee.employee_id:
                    errors.append("employee cannot manage or direct itself")

        for material in world.materials:
            organization = organizations.get(material.primary_inventory_organization_id)
            if organization is None or organization.organization_type != "INVENTORY_ORG":
                errors.append("material primary organization must be an inventory organization")

        active_material_projects: dict[Any, set[Any]] = defaultdict(set)
        for row in world.material_projects:
            if row.material_id not in materials or row.project_id not in projects:
                errors.append("material-project has a missing endpoint")
            if row.organization_id not in organizations:
                errors.append("material-project organization does not exist")
            if _active(row, as_of):
                active_material_projects[row.material_id].add(row.project_id)
        if any(not active_material_projects[material_id] for material_id in materials):
            errors.append("every material must connect to at least one project")
        connected_projects = set().union(*active_material_projects.values()) if materials else set()
        if connected_projects != set(projects):
            errors.append("every project must connect to at least one material")

        active_mpm = Counter()
        periods: dict[Any, list[tuple[date, date | None]]] = defaultdict(list)
        for row in world.material_mpm_assignments:
            if row.material_id not in materials or row.employee_id not in employees:
                errors.append("material MPM assignment has a missing endpoint")
            if _active(row, as_of):
                active_mpm[row.material_id] += 1
            periods[row.material_id].append((row.effective_from, row.effective_to))
        if any(active_mpm[material_id] != 1 for material_id in materials):
            errors.append("every material must have exactly one active MPM")
        for material_periods in periods.values():
            ordered = sorted(material_periods)
            for (_, previous_to), (current_from, _) in zip(ordered, ordered[1:]):
                if previous_to is None or current_from < previous_to:
                    errors.append("material MPM periods overlap")

        active_primary_suppliers = Counter()
        connected_suppliers: set[Any] = set()
        for row in world.material_supplier_assignments:
            if row.material_id not in materials or row.supplier_id not in suppliers:
                errors.append("material-supplier assignment has a missing endpoint")
            material = materials.get(row.material_id)
            if material and row.organization_id != material.primary_inventory_organization_id:
                errors.append("material supplier organization is not the material primary org")
            if _active(row, as_of):
                connected_suppliers.add(row.supplier_id)
                if row.assignment_type == "PRIMARY":
                    active_primary_suppliers[row.material_id] += 1
        if any(active_primary_suppliers[material_id] != 1 for material_id in materials):
            errors.append("every material must have exactly one active primary supplier")
        if connected_suppliers != set(suppliers):
            errors.append("every supplier must be connected")

        active_primary_customers = Counter()
        connected_customers: set[Any] = set()
        for row in world.project_customers:
            if row.project_id not in projects or row.customer_id not in customers:
                errors.append("project-customer assignment has a missing endpoint")
            if _active(row, as_of):
                connected_customers.add(row.customer_id)
                if row.relationship_type == "PRIMARY":
                    active_primary_customers[row.project_id] += 1
        if any(active_primary_customers[project_id] != 1 for project_id in projects):
            errors.append("every project must have exactly one active primary customer")
        if connected_customers != set(customers):
            errors.append("every customer must be connected")

        required_responsibilities = {"BUYER", "MATERIAL_CONTROLLER"}
        responsibilities: dict[Any, Counter[str]] = defaultdict(Counter)
        for row in world.material_responsibility_assignments:
            if row.material_id not in materials or row.employee_id not in employees:
                errors.append("material responsibility has a missing endpoint")
            material = materials.get(row.material_id)
            if material and row.organization_id != material.primary_inventory_organization_id:
                errors.append("material responsibility organization is not the primary org")
            if _active(row, as_of):
                responsibilities[row.material_id][row.responsibility_type] += 1
        for material_id in materials:
            if any(responsibilities[material_id][role] != 1 for role in required_responsibilities):
                errors.append("each material needs one active buyer and material controller")

        role_employee_ids = {row.employee_id for row in world.employee_role_assignments}
        if not role_employee_ids <= set(employees):
            errors.append("employee role assignment has a missing employee")
        if any(row.organization_id not in organizations for row in world.employee_role_assignments):
            errors.append("employee role assignment has a missing organization")

        text_values = [
            str(value)
            for row in world.all_records()
            for column in row.__table__.columns
            if isinstance((value := getattr(row, column.key)), str)
        ]
        if any(":\\" in value or value.startswith("/") for value in text_values):
            errors.append("generated business data contains an absolute filesystem path")

        if errors:
            raise MasterWorldValidationError("; ".join(dict.fromkeys(errors)))
