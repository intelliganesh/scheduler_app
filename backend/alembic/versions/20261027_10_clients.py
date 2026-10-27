"""add clients, client emails, and job client selections"""
from alembic import op
import sqlalchemy as sa

revision = "20261027_10"
down_revision = "20261027_09"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("client_code", sa.String(length=80), nullable=False),
        sa.Column("client_name", sa.Unicode(length=160), nullable=False),
    )
    op.create_index("ix_clients_company_id", "clients", ["company_id"])
    op.create_table("client_emails",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
    )
    op.create_index("ix_client_emails_client_id", "client_emails", ["client_id"])
    op.add_column("report_jobs", sa.Column("client_selections", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("report_jobs", "client_selections")
    op.drop_index("ix_client_emails_client_id", table_name="client_emails")
    op.drop_table("client_emails")
    op.drop_index("ix_clients_company_id", table_name="clients")
    op.drop_table("clients")
