"""add optional paydate to employees for export testing"""

from alembic import op
import sqlalchemy as sa


revision = "20261027_14"
down_revision = "20261027_13"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("employees", sa.Column("paydate", sa.DateTime(), nullable=True))
    op.create_index("ix_employees_paydate", "employees", ["paydate"])


def downgrade():
    op.drop_index("ix_employees_paydate", table_name="employees")
    op.drop_column("employees", "paydate")
