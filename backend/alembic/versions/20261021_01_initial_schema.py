"""create reports and users tables

Revision ID: 20261021_01
Revises:
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa

revision = "20261021_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("reports", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("title", sa.String(255), nullable=False), sa.Column("description", sa.Text(), nullable=True), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("username", sa.String(128), nullable=False), sa.Column("email", sa.String(255), nullable=True), sa.Column("full_name", sa.String(255), nullable=True), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("username"), sa.UniqueConstraint("email"))
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
    op.drop_table("reports")
