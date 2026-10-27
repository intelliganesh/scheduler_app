"""store split output manifest on job runs"""
from alembic import op
import sqlalchemy as sa

revision = "20261027_13"
down_revision = "20261027_12"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("job_runs", sa.Column("output_manifest", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("job_runs", "output_manifest")
