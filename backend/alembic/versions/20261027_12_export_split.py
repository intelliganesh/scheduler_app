"""add export split preference to report jobs"""
from alembic import op
import sqlalchemy as sa

revision = "20261027_12"
down_revision = "20261027_10"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("report_jobs", sa.Column("export_split_by", sa.String(length=20), nullable=True))


def downgrade():
    op.drop_column("report_jobs", "export_split_by")
