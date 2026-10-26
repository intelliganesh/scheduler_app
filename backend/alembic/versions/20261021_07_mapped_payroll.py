"""add TXT column metadata and a mapping-aware payroll procedure"""
from alembic import op
import sqlalchemy as sa


revision = "20261021_07"
down_revision = "20261021_06"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("uploaded_queries", sa.Column("column_names", sa.Text(), nullable=True))
    op.add_column("report_jobs", sa.Column("column_mappings", sa.Text(), nullable=True))
    if op.get_bind().dialect.name != "mssql":
        return
    op.execute(r"""
CREATE OR ALTER PROCEDURE dbo.usp_GenerateMappedPayrollReport
    @company_id INT,
    @column_mappings NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    IF ISJSON(@column_mappings) <> 1
        THROW 50001, 'Column mappings must be valid JSON.', 1;

    DECLARE @requested TABLE (
        ordinal INT NOT NULL,
        display_name NVARCHAR(160) NOT NULL,
        database_field SYSNAME NOT NULL
    );
    INSERT INTO @requested (ordinal, display_name, database_field)
    SELECT CONVERT(INT, value.[key]), parsed.display_name, parsed.database_field
    FROM OPENJSON(@column_mappings) AS value
    CROSS APPLY OPENJSON(value.value)
      WITH (display_name NVARCHAR(160) '$.display_name', database_field SYSNAME '$.database_field') AS parsed;

    IF NOT EXISTS (SELECT 1 FROM @requested)
        THROW 50002, 'At least one column mapping is required.', 1;
    IF EXISTS (SELECT database_field FROM @requested GROUP BY database_field HAVING COUNT(*) > 1)
        THROW 50003, 'Database fields must be mapped one-to-one.', 1;
    IF EXISTS (SELECT display_name FROM @requested GROUP BY display_name HAVING COUNT(*) > 1)
        THROW 50004, 'TXT column names must be unique.', 1;
    IF EXISTS (SELECT 1 FROM @requested WHERE database_field NOT IN
      ('employee_code','employee_name','department','designation','payroll_month','basic_salary','allowances','deductions','net_salary','payment_status'))
        THROW 50005, 'The requested database field is not approved.', 1;

    DECLARE @select_list NVARCHAR(MAX);
    SELECT @select_list = STUFF((
        SELECT N', ' + CASE database_field
          WHEN 'employee_code' THEN N'e.employee_code'
          WHEN 'employee_name' THEN N'e.employee_name'
          WHEN 'department' THEN N'e.department'
          WHEN 'designation' THEN N'e.designation'
          WHEN 'payroll_month' THEN N'p.payroll_month'
          WHEN 'basic_salary' THEN N'p.basic_salary'
          WHEN 'allowances' THEN N'p.allowances'
          WHEN 'deductions' THEN N'p.deductions'
          WHEN 'net_salary' THEN N'p.net_salary'
          WHEN 'payment_status' THEN N'p.payment_status'
        END + N' AS ' + QUOTENAME(display_name)
        FROM @requested ORDER BY ordinal FOR XML PATH(''), TYPE).value('.', 'NVARCHAR(MAX)'), 1, 2, N'');

    DECLARE @sql NVARCHAR(MAX) = N'SELECT ' + @select_list + N'
      FROM employees e JOIN payroll p ON p.employee_id = e.id
      WHERE e.company_id = @company_id
        AND p.payroll_month = (SELECT MAX(p2.payroll_month) FROM payroll p2 JOIN employees e2 ON e2.id = p2.employee_id WHERE e2.company_id = @company_id)
      ORDER BY e.employee_code;';
    EXEC sys.sp_executesql @sql, N'@company_id INT', @company_id = @company_id;
END
""")


def downgrade():
    if op.get_bind().dialect.name == "mssql":
        op.execute("DROP PROCEDURE IF EXISTS dbo.usp_GenerateMappedPayrollReport")
    op.drop_column("report_jobs", "column_mappings")
    op.drop_column("uploaded_queries", "column_names")
