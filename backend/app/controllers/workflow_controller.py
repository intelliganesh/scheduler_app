from app.schemas.workflow import JobCreate
from app.services.workflow_service import APPROVED_PROCEDURES, MAPPING_FIELDS, MAPPING_PROCEDURE, WorkflowService
from app.services.scheduler_service import get_scheduler


class WorkflowController:
    def __init__(self, service=None): self.service = service or WorkflowService()
    def companies(self, db): return self.service.repository.companies(db)
    def jobs(self, db): return self.service.repository.jobs(db)
    def stats(self, db):
        data = self.service.repository.stats(db); data["recent_runs"] = self.service.repository.runs(db)[:10]; return data
    def procedures(self):
        return [{"key": key, "name": name, "supports_mapping": key == MAPPING_PROCEDURE, "allowed_fields": list(MAPPING_FIELDS) if key == MAPPING_PROCEDURE else []} for key, name in APPROVED_PROCEDURES.items()]
    def create_job(self, db, payload: JobCreate):
        job = self.service.create_job(db, payload)
        scheduler = get_scheduler()
        if scheduler.scheduler.running:
            scheduler.sync_job(job)
        return job
    def upload(self, db, name, content): return self.service.create_upload(db, name, content)
    def enable(self, db, job_id, enabled): return self.service.set_enabled(db, job_id, enabled)
    def run(self, db, job_id, retry_run_id=None): return self.service.run_job(db, job_id, retry_run_id)
    def runs(self, db, failed_before=None): return self.service.repository.runs(db, failed_before)
    def files(self, db): return self.service.repository.files(db)
