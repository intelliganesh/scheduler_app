"""add Active Directory profile and permission columns to users

Revision ID: 20261021_03
Revises: 20261021_02
Create Date: 2026-10-21

Additive only: every new column is nullable, so existing rows are unchanged.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261021_03"
down_revision = "20261021_02"
branch_labels = None
depends_on = None

PROFILE_COLUMNS = ("user_principal_name", "given_name", "surname", "department", "title", "company")


def upgrade() -> None:
    for name in PROFILE_COLUMNS:
        op.add_column("users", sa.Column(name, sa.Unicode(255), nullable=True))
    op.add_column("users", sa.Column("permissions", sa.Unicode(1000), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "permissions")
    for name in reversed(PROFILE_COLUMNS):
        op.drop_column("users", name)
