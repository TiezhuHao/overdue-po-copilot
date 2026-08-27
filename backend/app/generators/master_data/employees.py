from datetime import timedelta

from app.generators.context import GenerationContext
from app.models.platform import Employee, EmployeeRoleAssignment, Organization


ROLE_EMPLOYEE_INDEXES = {
    "BUYER": (2, 3),
    "MATERIAL_CONTROLLER": (4, 5),
    "PRIMARY_MATERIAL_CONTROLLER": (6, 7),
    "RESEARCH_REPRESENTATIVE": (8,),
}


def generate_employees(
    context: GenerationContext,
    organizations: list[Organization],
) -> tuple[list[Employee], list[EmployeeRoleAssignment]]:
    leaf_organizations = [
        organization
        for organization in organizations
        if organization.organization_type in {"DEPARTMENT", "PLANNING_DEPARTMENT"}
    ]
    employee_ids = [
        context.entity_id("employee", f"EMP-{index:04d}")
        for index in range(1, context.config.employee_count + 1)
    ]
    employees: list[Employee] = []
    for index, employee_id in enumerate(employee_ids, start=1):
        code = f"EMP-{index:04d}"
        organization = leaf_organizations[(index - 1) % len(leaf_organizations)]
        if index == 1:
            manager_id = None
            director_id = None
        elif index <= 5:
            manager_id = employee_ids[0]
            director_id = employee_ids[0]
        else:
            manager_id = employee_ids[1 + ((index - 6) % min(4, len(employee_ids) - 1))]
            director_id = employee_ids[0]
        employees.append(
            Employee(
                dataset_version_id=context.dataset_version_id,
                employee_id=employee_id,
                employee_code=code,
                account_name=f"synthetic.employee{index:04d}",
                employee_name=f"Synthetic Employee {index:04d}",
                organization_id=organization.organization_id,
                manager_employee_id=manager_id,
                director_employee_id=director_id,
                is_active=True,
            )
        )

    effective_from = context.config.snapshot_date - timedelta(days=730)
    roles: list[EmployeeRoleAssignment] = []
    for role_type, indexes in ROLE_EMPLOYEE_INDEXES.items():
        for index in indexes:
            employee = employees[index - 1]
            stable_key = f"{employee.employee_code}:{role_type}"
            roles.append(
                EmployeeRoleAssignment(
                    dataset_version_id=context.dataset_version_id,
                    employee_role_assignment_id=context.entity_id(
                        "employee_role_assignment", stable_key
                    ),
                    employee_id=employee.employee_id,
                    organization_id=employee.organization_id,
                    role_type=role_type,
                    effective_from=effective_from,
                    effective_to=None,
                )
            )
    return employees, roles

