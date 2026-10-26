from alembic import context

from app.config.settings import get_settings
from app.database.base import Base
import app.models  # noqa: F401

config = context.config
# Keep the URL out of Alembic's ConfigParser: URL-encoded passwords contain "%",
# which breaks interpolation and would surface the credentials in tracebacks.
database_url = get_settings().sqlalchemy_url
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = context.config.attributes.get("connection")
    if connectable is None:
        from sqlalchemy import create_engine, pool
        connectable = create_engine(database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
