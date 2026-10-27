"""store report sorting and numeric filtering options"""

from alembic import op
import sqlalchemy as sa

revision = "20261027_16"
down_revision = "20261027_15"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("report_jobs", sa.Column("report_options", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("report_jobs", "report_options")
