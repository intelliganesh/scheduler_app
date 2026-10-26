"""add one-time schedule timestamp"""
from alembic import op
import sqlalchemy as sa
revision = "20261021_05"
down_revision = "20261021_04"
branch_labels = None
depends_on = None
def upgrade(): op.add_column("report_jobs", sa.Column("schedule_at", sa.DateTime(), nullable=True))
def downgrade(): op.drop_column("report_jobs", "schedule_at")
