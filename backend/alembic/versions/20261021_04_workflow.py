"""workflow proof of concept tables and SQL Server read-only procedures"""
from alembic import op
import sqlalchemy as sa

revision = "20261021_04"
down_revision = "20261021_03"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("companies", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_name", sa.String(120), nullable=False, unique=True))
    op.create_index("ix_companies_company_name", "companies", ["company_name"])
    op.create_table("sample_sales", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False), sa.Column("product_name", sa.String(160), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False), sa.Column("amount", sa.Float(), nullable=False), sa.Column("sale_date", sa.DateTime(), nullable=False))
    op.create_index("ix_sample_sales_company_id", "sample_sales", ["company_id"])
    op.create_table("uploaded_queries", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("original_name", sa.String(255), nullable=False), sa.Column("stored_name", sa.String(255), nullable=False, unique=True), sa.Column("approved_key", sa.String(80), nullable=False), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_table("report_jobs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("title", sa.String(160), nullable=False), sa.Column("display_name", sa.String(160), nullable=False), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False), sa.Column("source_type", sa.String(20), nullable=False), sa.Column("source_key", sa.String(80)), sa.Column("uploaded_query_id", sa.Integer(), sa.ForeignKey("uploaded_queries.id")), sa.Column("schedule_time", sa.String(5), nullable=False), sa.Column("recurrence", sa.String(12), nullable=False), sa.Column("day_of_week", sa.Integer()), sa.Column("day_of_month", sa.Integer()), sa.Column("recipients", sa.Text()), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("next_run_at", sa.DateTime()), sa.Column("last_run_status", sa.String(30)), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_report_jobs_title", "report_jobs", ["title"]); op.create_index("ix_report_jobs_company_id", "report_jobs", ["company_id"])
    op.create_table("job_runs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("job_id", sa.Integer(), sa.ForeignKey("report_jobs.id"), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("current_step", sa.String(80)), sa.Column("error_message", sa.Text()), sa.Column("step_log", sa.Text(), nullable=False), sa.Column("csv_content", sa.Text()), sa.Column("started_at", sa.DateTime(), server_default=sa.func.now()), sa.Column("completed_at", sa.DateTime()))
    op.create_index("ix_job_runs_job_id", "job_runs", ["job_id"])
    op.create_table("generated_files", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("run_id", sa.Integer(), sa.ForeignKey("job_runs.id"), nullable=False, unique=True), sa.Column("job_id", sa.Integer(), sa.ForeignKey("report_jobs.id"), nullable=False), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False), sa.Column("file_name", sa.String(255), nullable=False, unique=True), sa.Column("storage_path", sa.String(500), nullable=False), sa.Column("row_count", sa.Integer(), nullable=False), sa.Column("file_size", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_generated_files_job_id", "generated_files", ["job_id"]); op.create_index("ix_generated_files_company_id", "generated_files", ["company_id"])
    if op.get_bind().dialect.name == "mssql":
        op.execute("CREATE OR ALTER PROCEDURE dbo.usp_SalesByCompany @company_id INT AS SELECT product_name, quantity, amount, sale_date FROM sample_sales WHERE company_id=@company_id ORDER BY sale_date DESC")
        op.execute("CREATE OR ALTER PROCEDURE dbo.usp_MonthlySalesSummary @company_id INT AS SELECT product_name, SUM(quantity) AS quantity, SUM(amount) AS amount, MAX(sale_date) AS sale_date FROM sample_sales WHERE company_id=@company_id GROUP BY product_name")
        op.execute("CREATE OR ALTER PROCEDURE dbo.usp_ProductSalesReport @company_id INT AS SELECT product_name, quantity, amount, sale_date FROM sample_sales WHERE company_id=@company_id ORDER BY product_name")

def downgrade():
    for table in ("generated_files", "job_runs", "report_jobs", "uploaded_queries", "sample_sales", "companies"): op.drop_table(table)
