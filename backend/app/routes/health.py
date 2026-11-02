from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.utils.query_store import query_store

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.get("/health/database")
def database_health_check(db: Session = Depends(get_db)):
    """Runs a minimal query without exposing connection details."""
    try:
        db.execute(text(query_store.get("1")))
        return {"status": "ok", "database": "reachable"}
    except (SQLAlchemyError, OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database is unavailable.") from exc
