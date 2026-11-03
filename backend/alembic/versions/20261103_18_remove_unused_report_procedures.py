"""remove report procedures no longer used by the application"""

from alembic import op


revision = "20261103_18"
down_revision = "20261028_17"
branch_labels = None
depends_on = None


UNUSED_PROCEDURES = (
    "usp_DepartmentPayrollReport",
    "usp_EmployeePayrollReport",
    "usp_EmployeeSalaryBreakdown",
    "usp_GenerateMappedPayrollReport",
    "usp_MonthlyPayrollSummary",
    "usp_MonthlySalesSummary",
    "usp_ProductSalesReport",
    "usp_SalesByCompany",
)


def upgrade():
    if op.get_bind().dialect.name == "mssql":
        for name in UNUSED_PROCEDURES:
            op.execute(f"DROP PROCEDURE IF EXISTS dbo.{name}")


def downgrade():
    # The retired procedures are intentionally not recreated. Their original
    # definitions remain in the historical migrations for auditability, while
    # this cleanup migration keeps upgrades from restoring unused objects.
    pass
