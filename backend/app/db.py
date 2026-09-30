from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

# The engine manages the pool of connections to PostgreSQL.
# pool_pre_ping checks a connection is still alive before using it.
engine = create_engine(settings.database_url, pool_pre_ping=True)

# A session is one "conversation" with the database (usually one per request).
SessionLocal = sessionmaker(bind=engine, autoflush=False)


def get_db():
    """FastAPI dependency: give the endpoint a session, always close it after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
