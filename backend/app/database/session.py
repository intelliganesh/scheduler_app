from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings

settings = get_settings()
engine = create_engine(settings.sqlalchemy_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Provide one database session per request and always close it."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
