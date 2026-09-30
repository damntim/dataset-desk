from alembic import context
from sqlalchemy import create_engine

from app.config import settings
from app.models import Base

# Alembic compares this (our Python models) with the real database
# to work out which changes a new migration must contain.
target_metadata = Base.metadata


def run_migrations_online() -> None:
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
