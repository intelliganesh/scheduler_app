"""Install the database schema/procedures and seed the demo data.

Run from the backend directory with::

    .venv/bin/python seed.py

The command is safe to run repeatedly.  Alembic applies only outstanding
migrations, and ``WorkflowService.seed`` only creates missing demo datasets.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# Allow ``python backend/seed.py`` as well as ``python seed.py`` from backend/.
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from alembic import command
from alembic.config import Config

from app.config.settings import get_settings
from app.database.session import SessionLocal
from app.models.workflow import Client, Company, Employee, Payroll, SampleSale
from app.services.workflow_service import WorkflowService


def apply_schema_and_procedures() -> None:
    """Apply all migrations, including SQL Server stored procedures."""
    alembic_config = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(alembic_config, "head")


def seed_database() -> dict[str, int]:
    """Install database objects and populate every built-in demo dataset."""
    apply_schema_and_procedures()

    db = SessionLocal()
    try:
        WorkflowService().seed(db)
        return {
            "companies": db.query(Company).count(),
            "sample_sales": db.query(SampleSale).count(),
            "clients": db.query(Client).count(),
            "employees": db.query(Employee).count(),
            "payroll": db.query(Payroll).count(),
        }
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    settings = get_settings()
    print(f"Seeding {settings.db_dialect} database '{settings.db_name}'...")
    counts = seed_database()
    for table, count in counts.items():
        print(f"  {table}: {count}")
    if settings.db_dialect.lower() in {"mssql", "sqlserver"}:
        print("  SQL Server stored procedures: installed/updated")
    else:
        print("  stored procedures: skipped (only supported by SQL Server migrations)")
    print("Seed completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
