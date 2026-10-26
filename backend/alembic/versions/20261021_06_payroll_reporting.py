"""fictional payroll demo tables and approved read-only procedures"""
from alembic import op
import sqlalchemy as sa

revision = "20261021_06"
down_revision = "20261021_05"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_code", sa.String(40), nullable=False, unique=True),
        sa.Column("employee_name", sa.Unicode(160), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("department", sa.Unicode(100), nullable=False),
        sa.Column("designation", sa.Unicode(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_employees_employee_code", "employees", ["employee_code"])
    op.create_index("ix_employees_company_id", "employees", ["company_id"])
    op.create_index("ix_employees_is_active", "employees", ["is_active"])
    op.create_table(
        "payroll",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("payroll_month", sa.DateTime(), nullable=False),
        sa.Column("basic_salary", sa.Numeric(12, 2), nullable=False),
        sa.Column("allowances", sa.Numeric(12, 2), nullable=False),
        sa.Column("deductions", sa.Numeric(12, 2), nullable=False),
        sa.Column("net_salary", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_status", sa.String(30), nullable=False),
    )
    op.create_index("ix_payroll_employee_id", "payroll", ["employee_id"])
    op.create_index("ix_payroll_payroll_month", "payroll", ["payroll_month"])
    op.create_index("ix_payroll_employee_month", "payroll", ["employee_id", "payroll_month"], unique=True)
    if op.get_bind().dialect.name == "mssql":
        op.execute("""CREATE OR ALTER PROCEDURE dbo.usp_EmployeePayrollReport @company_id INT AS
BEGIN SET NOCOUNT ON;
SELECT e.employee_code AS employee_id, e.employee_name, e.department, e.designation, p.payroll_month,
       p.basic_salary, p.allowances, p.deductions, p.net_salary, p.payment_status
FROM employees e JOIN payroll p ON p.employee_id=e.id
WHERE e.company_id=@company_id AND p.payroll_month=(SELECT MAX(p2.payroll_month) FROM payroll p2 JOIN employees e2 ON e2.id=p2.employee_id WHERE e2.company_id=@company_id)
ORDER BY e.employee_code; END""")
        op.execute("""CREATE OR ALTER PROCEDURE dbo.usp_MonthlyPayrollSummary @company_id INT AS
BEGIN SET NOCOUNT ON;
SELECT p.payroll_month, COUNT(*) AS employee_count, SUM(p.basic_salary) AS basic_salary_total,
       SUM(p.allowances) AS allowances_total, SUM(p.deductions) AS deductions_total, SUM(p.net_salary) AS net_salary_total
FROM employees e JOIN payroll p ON p.employee_id=e.id WHERE e.company_id=@company_id
GROUP BY p.payroll_month ORDER BY p.payroll_month DESC; END""")
        op.execute("""CREATE OR ALTER PROCEDURE dbo.usp_DepartmentPayrollReport @company_id INT AS
BEGIN SET NOCOUNT ON;
SELECT e.department, p.payroll_month, COUNT(*) AS employee_count, SUM(p.net_salary) AS net_salary_total
FROM employees e JOIN payroll p ON p.employee_id=e.id WHERE e.company_id=@company_id
  AND p.payroll_month=(SELECT MAX(p2.payroll_month) FROM payroll p2 JOIN employees e2 ON e2.id=p2.employee_id WHERE e2.company_id=@company_id)
GROUP BY e.department, p.payroll_month ORDER BY e.department; END""")
        op.execute("""CREATE OR ALTER PROCEDURE dbo.usp_EmployeeSalaryBreakdown @company_id INT AS
BEGIN SET NOCOUNT ON;
SELECT e.employee_code AS employee_id, e.employee_name, e.department, e.designation, p.payroll_month,
       p.basic_salary, p.allowances, p.deductions, p.net_salary, p.payment_status
FROM employees e JOIN payroll p ON p.employee_id=e.id WHERE e.company_id=@company_id ORDER BY e.employee_code, p.payroll_month DESC; END""")
        op.execute("""CREATE OR ALTER PROCEDURE dbo.usp_CompanyPayrollReport @company_id INT AS
BEGIN SET NOCOUNT ON;
SELECT c.company_name, p.payroll_month, COUNT(*) AS employee_count, SUM(p.net_salary) AS net_salary_total
FROM companies c JOIN employees e ON e.company_id=c.id JOIN payroll p ON p.employee_id=e.id
WHERE c.id=@company_id GROUP BY c.company_name, p.payroll_month ORDER BY p.payroll_month DESC; END""")


def downgrade():
    if op.get_bind().dialect.name == "mssql":
        for name in ("usp_EmployeePayrollReport", "usp_MonthlyPayrollSummary", "usp_DepartmentPayrollReport", "usp_EmployeeSalaryBreakdown", "usp_CompanyPayrollReport"):
            op.execute(f"DROP PROCEDURE IF EXISTS dbo.{name}")
    op.drop_index("ix_payroll_employee_month", table_name="payroll")
    op.drop_index("ix_payroll_payroll_month", table_name="payroll")
    op.drop_index("ix_payroll_employee_id", table_name="payroll")
    op.drop_table("payroll")
    op.drop_index("ix_employees_is_active", table_name="employees")
    op.drop_index("ix_employees_company_id", table_name="employees")
    op.drop_index("ix_employees_employee_code", table_name="employees")
    op.drop_table("employees")
