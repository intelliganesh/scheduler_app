"""allow the every-two-minutes recurrence value"""

from alembic import op
import sqlalchemy as sa


revision = "20261027_15"
down_revision = "20261027_14"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "report_jobs",
        "recurrence",
        existing_type=sa.String(length=12),
        type_=sa.String(length=20),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "report_jobs",
        "recurrence",
        existing_type=sa.String(length=20),
        type_=sa.String(length=12),
        existing_nullable=False,
    )
