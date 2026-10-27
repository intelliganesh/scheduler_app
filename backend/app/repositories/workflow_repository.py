from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.workflow import Client, ClientEmail, Company, GeneratedFile, JobRun, ReportJob, SampleSale, UploadedQuery


class WorkflowRepository:
    def companies(self, db: Session): return list(db.scalars(select(Company).order_by(Company.company_name)))
    def clients(self, db: Session, company_id: int): return list(db.scalars(select(Client).where(Client.company_id == company_id).order_by(Client.client_name)))
    def client_emails(self, db: Session, client_id: int): return list(db.scalars(select(ClientEmail).where(ClientEmail.client_id == client_id).order_by(ClientEmail.email)))
    def company_emails(self, db: Session, company_id: int):
        return list(db.scalars(select(ClientEmail).join(Client, ClientEmail.client_id == Client.id).where(Client.company_id == company_id).order_by(ClientEmail.email)))
    def jobs(self, db: Session): return list(db.scalars(select(ReportJob).order_by(ReportJob.id.desc())))
    def job(self, db: Session, job_id: int): return db.get(ReportJob, job_id)
    def run(self, db: Session, run_id: int): return db.get(JobRun, run_id)
    def runs(self, db: Session, failed_before=None):
        query = select(JobRun).order_by(JobRun.id.desc())
        if failed_before: query = query.where(JobRun.status.in_(["Failed", "Partially Completed"]), JobRun.started_at <= failed_before)
        return list(db.scalars(query))
    def files(self, db: Session): return list(db.scalars(select(GeneratedFile).order_by(GeneratedFile.id.desc())))
    def file(self, db: Session, file_id: int): return db.get(GeneratedFile, file_id)
    def uploaded(self, db: Session, upload_id: int): return db.get(UploadedQuery, upload_id)
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
