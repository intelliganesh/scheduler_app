"""remove the unused sample sales table"""

from alembic import op


revision = "20261103_19"
down_revision = "20261103_18"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "mssql":
        op.execute("DROP TABLE IF EXISTS dbo.sample_sales")


def downgrade():
    # This table was demo-only and is intentionally not recreated.
    pass
