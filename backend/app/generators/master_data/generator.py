from app.generators.context import GenerationContext
from app.generators.master_data.customers import generate_customers
from app.generators.master_data.employees import generate_employees
from app.generators.master_data.materials import generate_materials
from app.generators.master_data.organizations import generate_organizations
from app.generators.master_data.projects import generate_projects
from app.generators.master_data.relationships import generate_relationships
from app.generators.master_data.suppliers import generate_suppliers
from app.generators.master_data.world import MasterWorld


class MasterDataGenerator:
    def generate(self, context: GenerationContext) -> MasterWorld:
        organizations = generate_organizations(context)
        employees, employee_roles = generate_employees(context, organizations)
        customers = generate_customers(context)
        suppliers = generate_suppliers(context)
        projects = generate_projects(context)
        materials = generate_materials(context, organizations)
        (
            material_projects,
            material_mpm_assignments,
            material_supplier_assignments,
            project_customers,
            material_responsibility_assignments,
        ) = generate_relationships(
            context,
            materials,
            projects,
            customers,
            suppliers,
            employees,
            employee_roles,
        )
        return MasterWorld(
            organizations=organizations,
            employees=employees,
            employee_role_assignments=employee_roles,
            customers=customers,
            suppliers=suppliers,
            projects=projects,
            materials=materials,
            material_projects=material_projects,
            material_mpm_assignments=material_mpm_assignments,
            material_supplier_assignments=material_supplier_assignments,
            project_customers=project_customers,
            material_responsibility_assignments=material_responsibility_assignments,
        )
