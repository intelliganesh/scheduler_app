from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials

from app.controllers.workflow_controller import WorkflowController
from app.database.session import get_db
from app.schemas.workflow import JobCreate, JobRead
from app.utils.security import bearer_scheme, get_token_claims

router = APIRouter(tags=["workflow"])
controller = WorkflowController()


def authorize(menu: str):
    def dependency(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
        if menu not in get_token_claims(credentials).get("menus", []): raise HTTPException(status_code=403, detail="You are not authorized for this menu.")
    return dependency

@router.get("/dashboard")
def dashboard(db=Depends(get_db), _: None = Depends(authorize("dashboard"))): return controller.stats(db)
@router.get("/companies")
def companies(db=Depends(get_db), _: None = Depends(authorize("create_job"))): return controller.companies(db)
@router.get("/approved-procedures")
def procedures(_: None = Depends(authorize("create_job"))): return controller.procedures()
@router.post("/uploads/query")
async def upload_query(file: UploadFile = File(...), db=Depends(get_db), _: None = Depends(authorize("create_job"))):
    try: return controller.upload(db, file.filename or "query.txt", await file.read())
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
@router.get("/jobs", response_model=list[JobRead])
def jobs(db=Depends(get_db), _: None = Depends(authorize("scheduled_jobs"))): return controller.jobs(db)
@router.post("/jobs", response_model=JobRead)
def create_job(payload: JobCreate, db=Depends(get_db), _: None = Depends(authorize("create_job"))):
    try: return controller.create_job(db, payload)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
@router.post("/jobs/{job_id}/enabled", response_model=JobRead)
def enabled(job_id: int, enabled: bool, db=Depends(get_db), _: None = Depends(authorize("scheduled_jobs"))):
    try:
        return controller.enable(db, job_id, enabled)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
@router.post("/jobs/{job_id}/run")
def run(job_id: int, db=Depends(get_db), _: None = Depends(authorize("scheduled_jobs"))):
    try:
        return controller.run(db, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
@router.get("/runs")
def runs(failed_before: datetime | None = None, db=Depends(get_db), _: None = Depends(authorize("task_management"))): return controller.runs(db, failed_before)
@router.post("/runs/{run_id}/retry")
def retry(run_id: int, db=Depends(get_db), _: None = Depends(authorize("task_management"))):
    record = controller.service.repository.run(db, run_id)
    if not record: raise HTTPException(status_code=404, detail="Run not found.")
    try:
        return controller.run(db, record.job_id, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
@router.get("/files")
def files(db=Depends(get_db), _: None = Depends(authorize("generated_files"))): return controller.files(db)
@router.get("/files/{file_id}/download")
def download(file_id: int, db=Depends(get_db), _: None = Depends(authorize("generated_files"))):
    record = controller.service.repository.file(db, file_id)
    if not record or not Path(record.storage_path).is_file(): raise HTTPException(status_code=404, detail="Generated file is unavailable.")
    return FileResponse(record.storage_path, filename=record.file_name, media_type="text/csv")
