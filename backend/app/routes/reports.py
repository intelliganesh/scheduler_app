from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.controllers.report_controller import ReportController
from app.database.session import get_db
from app.schemas.report import ReportCreate, ReportRead
from app.utils.security import bearer_scheme, get_token_claims

router = APIRouter(prefix="/reports", tags=["reports"])
controller = ReportController()


def authorize_report(menu: str):
    def dependency(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
        if menu not in get_token_claims(credentials).get("menus", []):
            raise HTTPException(status_code=403, detail="You are not authorized for this menu.")
    return dependency


@router.get("", response_model=list[ReportRead])
def list_reports(db: Session = Depends(get_db), _: None = Depends(authorize_report("dashboard"))):
    return controller.list_reports(db)


@router.post("", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
def create_report(payload: ReportCreate, db: Session = Depends(get_db), _: None = Depends(authorize_report("create_job"))):
    return controller.create_report(db, payload)
