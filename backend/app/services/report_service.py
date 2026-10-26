from sqlalchemy.orm import Session

from app.models.report import Report
from app.repositories.report_repository import ReportRepository
from app.schemas.report import ReportCreate


class ReportService:
    def __init__(self, repository: ReportRepository | None = None):
        self.repository = repository or ReportRepository()

    def list_reports(self, db: Session) -> list[Report]:
        return self.repository.list(db)

    def create_report(self, db: Session, payload: ReportCreate) -> Report:
        # Put business rules here as the application grows.
        return self.repository.create(db, payload)
