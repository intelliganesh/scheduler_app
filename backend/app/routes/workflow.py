from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import logging

from app.controllers.workflow_controller import WorkflowController
from app.database.session import get_db
from app.schemas.workflow import JobCreate, JobRead, RunRead
from app.utils.security import bearer_scheme, get_token_claims

router = APIRouter(tags=["workflow"])
controller = WorkflowController()
frontend_logger = logging.getLogger("app.frontend")


class ClientErrorPayload(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    source: str = Field(default="window", max_length=80)


@router.post("/client-errors", status_code=204)
def client_error(payload: ClientErrorPayload, credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
    # Only signed-in browsers report errors; anonymous callers cannot write to the log.
    get_token_claims(credentials)
    frontend_logger.error("%s: %s", payload.source, payload.message)


MENU_ALIASES = {
    # Tokens issued before the Jobs consolidation may still contain these
    # legacy claims until they expire. They remain authorization aliases only;
    # they are not displayed as sidebar items.
    "jobs": {"jobs", "create_job", "scheduled_jobs", "task_management"},
}


def authorize(menu: str):
    def dependency(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
        granted = set(get_token_claims(credentials).get("menus", []))
        if not granted.intersection(MENU_ALIASES.get(menu, {menu})):
            raise HTTPException(status_code=403, detail="You are not authorized for this menu.")
    return dependency

@router.get("/dashboard")
def dashboard(db=Depends(get_db), _: None = Depends(authorize("dashboard"))): return controller.stats(db)
@router.get("/companies")
def companies(db=Depends(get_db), _: None = Depends(authorize("jobs"))): return controller.companies(db)
@router.get("/companies/{company_id}/clients")
def clients(company_id: int, db=Depends(get_db), _: None = Depends(authorize("jobs"))): return controller.clients(db, company_id)
@router.get("/clients/{client_id}/emails")
def client_emails(client_id: int, db=Depends(get_db), _: None = Depends(authorize("jobs"))): return controller.client_emails(db, client_id)
@router.get("/companies/{company_id}/emails")
def company_emails(company_id: int, db=Depends(get_db), _: None = Depends(authorize("jobs"))): return controller.company_emails(db, company_id)
@router.get("/approved-procedures")
def procedures(_: None = Depends(authorize("jobs"))): return controller.procedures()
@router.post("/uploads/query")
async def upload_query(file: UploadFile = File(...), db=Depends(get_db), _: None = Depends(authorize("jobs"))):
    try: return controller.upload(db, file.filename or "query.txt", await file.read())
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
@router.get("/jobs", response_model=list[JobRead])
def jobs(db=Depends(get_db), _: None = Depends(authorize("jobs"))): return controller.jobs(db)
@router.post("/jobs", response_model=JobRead)
def create_job(payload: JobCreate, db=Depends(get_db), _: None = Depends(authorize("jobs"))):
    try: return controller.create_job(db, payload)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
@router.put("/jobs/{job_id}", response_model=JobRead)
def update_job(job_id: int, payload: JobCreate, db=Depends(get_db), _: None = Depends(authorize("jobs"))):
    try:
        return controller.update_job(db, job_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404 if str(exc) == "Job not found." else 422, detail=str(exc)) from exc
@router.post("/jobs/{job_id}/enabled", response_model=JobRead)
def enabled(job_id: int, enabled: bool, db=Depends(get_db), _: None = Depends(authorize("jobs"))):
    try:
        return controller.enable(db, job_id, enabled)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
@router.post("/jobs/{job_id}/run")
def run(job_id: int, db=Depends(get_db), _: None = Depends(authorize("jobs"))):
    try:
        return RunRead.model_validate(controller.run(db, job_id))
    except ValueError as exc:
        raise HTTPException(status_code=404 if str(exc) == "Job not found." else 422, detail=str(exc)) from exc
@router.get("/runs", response_model=list[RunRead])
def runs(failed_before: datetime | None = None, db=Depends(get_db), _: None = Depends(authorize("jobs"))): return controller.runs(db, failed_before)
@router.post("/runs/{run_id}/retry")
def retry(run_id: int, db=Depends(get_db), _: None = Depends(authorize("jobs"))):
    record = controller.service.repository.run(db, run_id)
    if not record: raise HTTPException(status_code=404, detail="Run not found.")
    try:
        return RunRead.model_validate(controller.run(db, record.job_id, run_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
@router.get("/files")
def files(db=Depends(get_db), _: None = Depends(authorize("generated_files"))): return controller.files(db)
@router.get("/deletion-center")
def deletion_summary(db=Depends(get_db), _: None = Depends(authorize("deletion_center"))): return controller.deletion_summary(db)
@router.delete("/deletion-center")
def delete_all_jobs_and_files(db=Depends(get_db), _: None = Depends(authorize("deletion_center"))):
    from app.services.scheduler_service import get_scheduler
    get_scheduler().remove_all_report_jobs()
    return controller.delete_all_jobs_and_files(db)
@router.get("/files/{file_id}/download")
def download(file_id: int, db=Depends(get_db), _: None = Depends(authorize("generated_files"))):
    record = controller.service.repository.file(db, file_id)
    if not record or not Path(record.storage_path).is_file(): raise HTTPException(status_code=404, detail="Generated file is unavailable.")
    media_type = "application/zip" if record.file_name.lower().endswith(".zip") else "text/csv"
    return FileResponse(record.storage_path, filename=record.file_name, media_type=media_type)
