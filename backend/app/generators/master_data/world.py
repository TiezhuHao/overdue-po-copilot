from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.inspection import inspect

from app.generators.signature import canonical_json, content_hash
from app.models.platform import (
    Customer,
    Employee,
    EmployeeRoleAssignment,
    Material,
    MaterialMpmAssignment,
    MaterialProject,
    MaterialResponsibilityAssignment,
    MaterialSupplierAssignment,
    Organization,
    Project,
    ProjectCustomer,
    Supplier,
)


@dataclass
class MasterWorld:
    organizations: list[Organization] = field(default_factory=list)
    employees: list[Employee] = field(default_factory=list)
    employee_role_assignments: list[EmployeeRoleAssignment] = field(default_factory=list)
    customers: list[Customer] = field(default_factory=list)
    suppliers: list[Supplier] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)
    materials: list[Material] = field(default_factory=list)
    material_projects: list[MaterialProject] = field(default_factory=list)
    material_mpm_assignments: list[MaterialMpmAssignment] = field(default_factory=list)
    material_supplier_assignments: list[MaterialSupplierAssignment] = field(
        default_factory=list
    )
    project_customers: list[ProjectCustomer] = field(default_factory=list)
    material_responsibility_assignments: list[MaterialResponsibilityAssignment] = field(
        default_factory=list
    )

    COLLECTION_NAMES = (
        "organizations",
        "employees",
        "employee_role_assignments",
        "customers",
        "suppliers",
        "projects",
        "materials",
        "material_projects",
        "material_mpm_assignments",
        "material_supplier_assignments",
        "project_customers",
        "material_responsibility_assignments",
    )

    def all_records(self) -> list[Any]:
        records: list[Any] = []
        for name in self.COLLECTION_NAMES:
            records.extend(getattr(self, name))
        return records

    def counts(self) -> dict[str, int]:
        return {name: len(getattr(self, name)) for name in self.COLLECTION_NAMES}

    @staticmethod
    def _record_payload(record: Any) -> dict[str, Any]:
        mapper = inspect(type(record))
        return {
            column.key: getattr(record, column.key)
            for column in mapper.columns
            if column.key != "created_at"
        }

    def hash_payload(self, generation_signature: str) -> dict[str, Any]:
        payload: dict[str, Any] = {"generation_signature": generation_signature}
        for name in self.COLLECTION_NAMES:
            rows = [self._record_payload(record) for record in getattr(self, name)]
            payload[name] = sorted(rows, key=canonical_json)
        return payload

    def master_content_hash(self, generation_signature: str) -> str:
        return content_hash(self.hash_payload(generation_signature))

