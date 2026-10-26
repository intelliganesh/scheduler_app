from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.report import Report
from app.schemas.report import ReportCreate


class ReportRepository:
    """Database operations for reports only."""

    def list(self, db: Session) -> list[Report]:
        return list(db.scalars(select(Report).order_by(Report.created_at.desc())))

    def create(self, db: Session, payload: ReportCreate) -> Report:
        report = Report(**payload.model_dump())
        db.add(report)
        db.commit()
        db.refresh(report)
        return report
