"""normalize legacy scalar job recipients to JSON arrays"""

import json

import sqlalchemy as sa
from alembic import op


revision = "20261023_08"
down_revision = "20261021_07"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, recipients FROM report_jobs WHERE recipients IS NOT NULL")).mappings().all()
    for row in rows:
        value = row["recipients"]
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = [value.strip()]
        if isinstance(parsed, str):
            parsed = [parsed]
        if isinstance(parsed, list):
            connection.execute(
                sa.text("UPDATE report_jobs SET recipients = :recipients WHERE id = :id"),
                {"id": row["id"], "recipients": json.dumps(parsed, ensure_ascii=False)},
            )


def downgrade():
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, recipients FROM report_jobs WHERE recipients IS NOT NULL")).mappings().all()
    for row in rows:
        try:
            parsed = json.loads(row["recipients"])
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, list):
            legacy = parsed[0] if parsed else None
            connection.execute(sa.text("UPDATE report_jobs SET recipients = :recipients WHERE id = :id"), {"id": row["id"], "recipients": legacy})
