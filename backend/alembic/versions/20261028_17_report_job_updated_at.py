"""track report-job configuration updates"""

from alembic import op
import sqlalchemy as sa


revision = "20261028_17"
down_revision = "20261027_16"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("report_jobs", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE report_jobs SET updated_at = created_at WHERE updated_at IS NULL")


def downgrade():
    op.drop_column("report_jobs", "updated_at")
