"""add optional CSV delimiter to report jobs"""
from alembic import op
import sqlalchemy as sa


revision = "20261027_09"
down_revision = "20261023_08"
branch_labels = None
depends_on = None


def upgrade():
    # Nullable keeps old jobs valid; the application treats NULL as comma.
    op.add_column("report_jobs", sa.Column("delimiter", sa.String(length=1), nullable=True))


def downgrade():
    op.drop_column("report_jobs", "delimiter")
