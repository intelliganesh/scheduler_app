"""store text as NVARCHAR and allow multiple NULL emails on SQL Server

Revision ID: 20261021_02
Revises: 20261021_01
Create Date: 2026-10-21

SQL Server only. VARCHAR columns silently replaced non-Latin characters with "?",
and the UNIQUE constraint on users.email allowed only one NULL. ALTER COLUMN keeps
existing rows; no table or row is dropped. MySQL already permits multiple NULLs in a
unique key and uses its own character set, so it is left unchanged.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261021_02"
down_revision = "20261021_01"
branch_labels = None
depends_on = None

TEXT_COLUMNS = [
    # table, column, old type, new type, nullable
    ("reports", "title", sa.String(255), sa.Unicode(255), False),
    ("reports", "description", sa.Text(), sa.UnicodeText(), True),
    ("users", "username", sa.String(128), sa.Unicode(128), False),
    ("users", "email", sa.String(255), sa.Unicode(255), True),
    ("users", "full_name", sa.String(255), sa.Unicode(255), True),
]


def _drop_unique_constraints(table: str, column: str) -> None:
    """The initial migration let SQL Server generate UNIQUE constraint names."""
    names = op.get_bind().execute(
        sa.text(
            "SELECT kc.name FROM sys.key_constraints kc "
            "JOIN sys.index_columns ic ON ic.object_id = kc.parent_object_id AND ic.index_id = kc.unique_index_id "
            "JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id "
            "WHERE kc.type = 'UQ' AND kc.parent_object_id = OBJECT_ID(:table) AND c.name = :column"
        ),
        {"table": table, "column": column},
    ).scalars().all()
    for name in names:
        op.drop_constraint(name, table, type_="unique")


def upgrade() -> None:
    if op.get_bind().dialect.name != "mssql":
        return
    # Indexes and constraints must be removed before their columns can change type.
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    _drop_unique_constraints("users", "username")
    _drop_unique_constraints("users", "email")
    for table, column, old_type, new_type, nullable in TEXT_COLUMNS:
        op.alter_column(table, column, type_=new_type, existing_type=old_type, existing_nullable=nullable)
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True, mssql_where=sa.text("email IS NOT NULL"))


def downgrade() -> None:
    if op.get_bind().dialect.name != "mssql":
        return
    # Converting back to VARCHAR loses non-Latin characters, and restoring the UNIQUE
    # constraint fails if more than one user has a NULL email.
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    for table, column, old_type, new_type, nullable in TEXT_COLUMNS:
        op.alter_column(table, column, type_=old_type, existing_type=new_type, existing_nullable=nullable)
    op.create_unique_constraint(None, "users", ["username"])
    op.create_unique_constraint(None, "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])
