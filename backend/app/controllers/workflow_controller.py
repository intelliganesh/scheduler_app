from app.schemas.workflow import JobCreate, RunRead
from app.services.workflow_service import APPROVED_PROCEDURES, MAPPING_FIELDS, MAPPING_PROCEDURE, WorkflowService
from app.services.scheduler_service import get_scheduler


class WorkflowController:
    def __init__(self, service=None): self.service = service or WorkflowService()
    def companies(self, db): return self.service.repository.companies(db)
    def clients(self, db, company_id): return self.service.repository.clients(db, company_id)
    def client_emails(self, db, client_id): return self.service.repository.client_emails(db, client_id)
    def company_emails(self, db, company_id): return self.service.repository.company_emails(db, company_id)
    def jobs(self, db): return self.service.repository.jobs(db)
    def stats(self, db):
        data = self.service.repository.stats(db); data["recent_runs"] = [RunRead.model_validate(run).model_dump() for run in self.service.repository.runs(db)[:10]]; return data
    def procedures(self):
        return [{"key": key, "name": name, "supports_mapping": key == MAPPING_PROCEDURE, "allowed_fields": list(MAPPING_FIELDS) if key == MAPPING_PROCEDURE else []} for key, name in APPROVED_PROCEDURES.items()]
    def _sync(self, db, job):
        """Register the job's current state with the scheduler and persist next_run_at."""
        scheduler = get_scheduler()
        if scheduler.scheduler.running:
            scheduler.sync_job(job)
            db.commit(); db.refresh(job)
        return job
    def create_job(self, db, payload: JobCreate):
        return self._sync(db, self.service.create_job(db, payload))
    def update_job(self, db, job_id, payload: JobCreate):
        return self._sync(db, self.service.update_job(db, job_id, payload))
    def upload(self, db, name, content): return self.service.create_upload(db, name, content)
    def enable(self, db, job_id, enabled): return self._sync(db, self.service.set_enabled(db, job_id, enabled))
    def run(self, db, job_id, retry_run_id=None): return self.service.run_job(db, job_id, retry_run_id)
    def deletion_summary(self, db): return self.service.deletion_summary(db)
    def delete_all_jobs_and_files(self, db): return self.service.delete_all_jobs_and_files(db)
    def runs(self, db, failed_before=None): return self.service.repository.runs(db, failed_before)
    def files(self, db): return self.service.repository.files(db)
