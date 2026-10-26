from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.schemas.report import ReportCreate, ReportRead
from app.services.report_service import ReportService
from app.utils.exceptions import DatabaseOperationError


class ReportController:
    def __init__(self, service: ReportService | None = None):
        self.service = service or ReportService()

    def list_reports(self, db: Session) -> list[ReportRead]:
        try:
            return self.service.list_reports(db)
        except SQLAlchemyError as exc:
            raise DatabaseOperationError("Could not fetch reports.") from exc

    def create_report(self, db: Session, payload: ReportCreate) -> ReportRead:
        try:
            return self.service.create_report(db, payload)
        except SQLAlchemyError as exc:
            db.rollback()
            raise DatabaseOperationError("Could not create the report.") from exc
