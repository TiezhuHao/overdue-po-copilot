from datetime import timedelta
from decimal import Decimal

from app.generators.context import GenerationContext
from app.models.platform import (
    Customer,
    Employee,
    EmployeeRoleAssignment,
    Material,
    MaterialMpmAssignment,
    MaterialProject,
    MaterialResponsibilityAssignment,
    MaterialSupplierAssignment,
    Project,
    ProjectCustomer,
    Supplier,
)


def _material_project_rows(
    context: GenerationContext,
    materials: list[Material],
    projects: list[Project],
) -> list[MaterialProject]:
    project_indexes: list[set[int]] = [set() for _ in materials]
    for project_index in range(len(projects)):
        project_indexes[project_index % len(materials)].add(project_index)
    for material_index in range(len(materials)):
        project_indexes[material_index].add(material_index % len(projects))

    rows: list[MaterialProject] = []
    effective_from = context.config.snapshot_date - timedelta(days=1095)
    for material_index, material in enumerate(materials):
        selected = project_indexes[material_index]
        minimum = max(context.config.min_projects_per_material, len(selected))
        maximum = context.config.max_projects_per_material
        target = context.rng.randint(minimum, maximum)
        available = [index for index in range(len(projects)) if index not in selected]
        if target > len(selected):
            selected.update(context.rng.sample(available, target - len(selected)))
        if material_index == 0 and len(projects) > 1 and len(selected) == 1:
            selected.add(1)
        for project_index in sorted(selected):
            project = projects[project_index]
            stable_key = f"{material.material_code}:{project.project_code}"
            rows.append(
                MaterialProject(
                    dataset_version_id=context.dataset_version_id,
                    material_project_id=context.entity_id("material_project", stable_key),
                    material_id=material.material_id,
                    project_id=project.project_id,
                    organization_id=material.primary_inventory_organization_id,
                    relationship_type="ACTIVE_USAGE",
                    effective_from=effective_from,
                    effective_to=None,
                )
            )
    return rows


def _material_mpm_rows(
    context: GenerationContext,
    materials: list[Material],
    employees: list[Employee],
    employee_roles: list[EmployeeRoleAssignment],
) -> list[MaterialMpmAssignment]:
    employee_by_id = {employee.employee_id: employee for employee in employees}
    mpm_ids = [
        role.employee_id
        for role in employee_roles
        if role.role_type == "PRIMARY_MATERIAL_CONTROLLER"
    ]
    if not mpm_ids:
        mpm_ids = [
            role.employee_id
            for role in employee_roles
            if role.role_type == "MATERIAL_CONTROLLER"
        ]
    mpm_employees = [employee_by_id[employee_id] for employee_id in mpm_ids]
    historical_switch_count = (
        max(1, len(materials) // 10)
        if context.config.generation_options.get("historical_mpm_switches", True)
        else 0
    )
    switch_date = context.config.snapshot_date - timedelta(days=180)
    rows: list[MaterialMpmAssignment] = []
    for index, material in enumerate(materials):
        active_employee = mpm_employees[index % len(mpm_employees)]
        if index < historical_switch_count:
            previous_employee = mpm_employees[(index + 1) % len(mpm_employees)]
            if previous_employee.employee_id == active_employee.employee_id:
                previous_employee = employees[(index + 2) % len(employees)]
            previous_key = f"{material.material_code}:historical:{previous_employee.employee_code}"
            rows.append(
                MaterialMpmAssignment(
                    dataset_version_id=context.dataset_version_id,
                    material_mpm_assignment_id=context.entity_id(
                        "material_mpm_assignment", previous_key
                    ),
                    material_id=material.material_id,
                    employee_id=previous_employee.employee_id,
                    effective_from=context.config.snapshot_date - timedelta(days=1095),
                    effective_to=switch_date,
                )
            )
            active_from = switch_date
        else:
            active_from = context.config.snapshot_date - timedelta(days=730)
        active_key = f"{material.material_code}:active:{active_employee.employee_code}"
        rows.append(
            MaterialMpmAssignment(
                dataset_version_id=context.dataset_version_id,
                material_mpm_assignment_id=context.entity_id(
                    "material_mpm_assignment", active_key
                ),
                material_id=material.material_id,
                employee_id=active_employee.employee_id,
                effective_from=active_from,
                effective_to=None,
            )
        )
    return rows


def _material_supplier_rows(
    context: GenerationContext,
    materials: list[Material],
    suppliers: list[Supplier],
) -> list[MaterialSupplierAssignment]:
    rows: list[MaterialSupplierAssignment] = []
    effective_from = context.config.snapshot_date - timedelta(days=730)
    alternate_ratio = int(
        context.config.generation_options.get("alternate_supplier_ratio_percent", 35)
    ) / 100
    for index, material in enumerate(materials):
        primary = suppliers[index % len(suppliers)]
        price = (Decimal(100 + context.rng.randint(0, 900)) / Decimal(10)).quantize(
            Decimal("0.0001")
        )
        primary_key = f"{material.material_code}:{primary.supplier_code}:PRIMARY"
        rows.append(
            MaterialSupplierAssignment(
                dataset_version_id=context.dataset_version_id,
                material_supplier_assignment_id=context.entity_id(
                    "material_supplier_assignment", primary_key
                ),
                material_id=material.material_id,
                supplier_id=primary.supplier_id,
                organization_id=material.primary_inventory_organization_id,
                assignment_type="PRIMARY",
                agreement_unit_price=price,
                currency_code=primary.currency_code,
                effective_from=effective_from,
                effective_to=None,
            )
        )
        if len(suppliers) > 1 and context.rng.random() < alternate_ratio:
            alternate = suppliers[(index + 1 + context.rng.randrange(len(suppliers) - 1)) % len(suppliers)]
            if alternate.supplier_id == primary.supplier_id:
                alternate = suppliers[(index + 1) % len(suppliers)]
            alternate_key = f"{material.material_code}:{alternate.supplier_code}:ALTERNATE"
            rows.append(
                MaterialSupplierAssignment(
                    dataset_version_id=context.dataset_version_id,
                    material_supplier_assignment_id=context.entity_id(
                        "material_supplier_assignment", alternate_key
                    ),
                    material_id=material.material_id,
                    supplier_id=alternate.supplier_id,
                    organization_id=material.primary_inventory_organization_id,
                    assignment_type="ALTERNATE",
                    agreement_unit_price=(price * Decimal("1.05")).quantize(
                        Decimal("0.0001")
                    ),
                    currency_code=alternate.currency_code,
                    effective_from=effective_from,
                    effective_to=None,
                )
            )
    return rows


def _project_customer_rows(
    context: GenerationContext,
    projects: list[Project],
    customers: list[Customer],
) -> list[ProjectCustomer]:
    rows: list[ProjectCustomer] = []
    effective_from = context.config.snapshot_date - timedelta(days=1095)
    for index, project in enumerate(projects):
        primary = customers[index % len(customers)]
        primary_key = f"{project.project_code}:{primary.customer_code}:PRIMARY"
        rows.append(
            ProjectCustomer(
                dataset_version_id=context.dataset_version_id,
                project_customer_id=context.entity_id("project_customer", primary_key),
                project_id=project.project_id,
                customer_id=primary.customer_id,
                relationship_type="PRIMARY",
                effective_from=effective_from,
                effective_to=None,
            )
        )
        if len(customers) > 1 and index % 5 == 0:
            secondary = customers[(index + 1) % len(customers)]
            secondary_key = f"{project.project_code}:{secondary.customer_code}:SECONDARY"
            rows.append(
                ProjectCustomer(
                    dataset_version_id=context.dataset_version_id,
                    project_customer_id=context.entity_id(
                        "project_customer", secondary_key
                    ),
                    project_id=project.project_id,
                    customer_id=secondary.customer_id,
                    relationship_type="SECONDARY",
                    effective_from=effective_from,
                    effective_to=None,
                )
            )
    return rows


def _material_responsibility_rows(
    context: GenerationContext,
    materials: list[Material],
    employee_roles: list[EmployeeRoleAssignment],
) -> list[MaterialResponsibilityAssignment]:
    role_pools = {
        role_type: [
            role.employee_id for role in employee_roles if role.role_type == role_type
        ]
        for role_type in (
            "BUYER",
            "MATERIAL_CONTROLLER",
            "PRIMARY_MATERIAL_CONTROLLER",
        )
    }
    effective_from = context.config.snapshot_date - timedelta(days=730)
    rows: list[MaterialResponsibilityAssignment] = []
    for material_index, material in enumerate(materials):
        for role_type, employee_ids in role_pools.items():
            employee_id = employee_ids[material_index % len(employee_ids)]
            stable_key = f"{material.material_code}:{role_type}"
            rows.append(
                MaterialResponsibilityAssignment(
                    dataset_version_id=context.dataset_version_id,
                    material_responsibility_assignment_id=context.entity_id(
                        "material_responsibility_assignment", stable_key
                    ),
                    material_id=material.material_id,
                    organization_id=material.primary_inventory_organization_id,
                    employee_id=employee_id,
                    responsibility_type=role_type,
                    effective_from=effective_from,
                    effective_to=None,
                )
            )
    return rows


def generate_relationships(
    context: GenerationContext,
    materials: list[Material],
    projects: list[Project],
    customers: list[Customer],
    suppliers: list[Supplier],
    employees: list[Employee],
    employee_roles: list[EmployeeRoleAssignment],
) -> tuple[
    list[MaterialProject],
    list[MaterialMpmAssignment],
    list[MaterialSupplierAssignment],
    list[ProjectCustomer],
    list[MaterialResponsibilityAssignment],
]:
    return (
        _material_project_rows(context, materials, projects),
        _material_mpm_rows(context, materials, employees, employee_roles),
        _material_supplier_rows(context, materials, suppliers),
        _project_customer_rows(context, projects, customers),
        _material_responsibility_rows(context, materials, employee_roles),
    )

