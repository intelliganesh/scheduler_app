from sqlalchemy import func, select
from app.utils.workflow_sql import get, records
from sqlalchemy.orm import Session

from app.models.workflow import Client, ClientEmail, Company, GeneratedFile, JobRun, ReportJob, SampleSale, UploadedQuery


class WorkflowRepository:
    def companies(self, db: Session): return records(db, Company, "8")
    def clients(self, db: Session, company_id: int): return records(db, Client, "9", {"company_id": company_id})
    def client_emails(self, db: Session, client_id: int): return records(db, ClientEmail, "10", {"client_id": client_id})
    def company_emails(self, db: Session, company_id: int):
        return records(db, ClientEmail, "10", {"company_id": company_id})
    def jobs(self, db: Session): return records(db, ReportJob, "11")
    def job(self, db: Session, job_id: int): return get(db, ReportJob, job_id)
    def run(self, db: Session, run_id: int): return get(db, JobRun, run_id)
    def runs(self, db: Session, failed_before=None):
        return records(db, JobRun, "18", {"failed_before": failed_before})
    def files(self, db: Session): return records(db, GeneratedFile, "21")
    def file(self, db: Session, file_id: int): return get(db, GeneratedFile, file_id)
    def uploaded(self, db: Session, upload_id: int): return get(db, UploadedQuery, upload_id)
    def stats(self, db: Session):
        return {
            "total_jobs": db.scalar(select(func.count(ReportJob.id))) or 0,
            # SQL Server does not accept the SQLite-style `IS 1` emitted by
            # SQLAlchemy for Boolean.is_(True); equality compiles correctly
            # for both SQL Server and SQLite.
            "active_scheduled_jobs": db.scalar(select(func.count(ReportJob.id)).where(ReportJob.enabled == True)) or 0,
            "completed_runs": db.scalar(select(func.count(JobRun.id)).where(JobRun.status == "Completed")) or 0,
            "failed_runs": db.scalar(select(func.count(JobRun.id)).where(JobRun.status.in_(["Failed", "Partially Completed"]))) or 0,
            "generated_files": db.scalar(select(func.count(GeneratedFile.id))) or 0,
        }
