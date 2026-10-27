from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config.settings import get_settings
from app.config.logging import configure_logging
from app.routes import auth, health, reports, workflow
from app.database.session import SessionLocal
from app.services.workflow_service import WorkflowService
from app.services.scheduler_service import get_scheduler
from app.utils.exceptions import DatabaseOperationError

settings = get_settings()
configure_logging(settings.log_dir)
backend_logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Tokens signed with a known or short secret could be forged by anyone.
    if not settings.jwt_secret_is_secure:
        raise RuntimeError("JWT_SECRET_KEY must be a random value of at least 32 characters; see backend/.env.example.")
    db = SessionLocal()
    try:
        WorkflowService().seed(db)
    finally:
        db.close()
    scheduler = get_scheduler(); scheduler.start(); scheduler.sync_all()
    yield
    scheduler.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    # FastAPI echoes the submitted values by default, which would return passwords.
    errors = [{key: error[key] for key in ("type", "loc", "msg", "ctx") if key in error} for error in exc.errors()]
    backend_logger.warning("Request validation failed: %s", errors)
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


@app.exception_handler(DatabaseOperationError)
async def database_error_handler(_: Request, exc: DatabaseOperationError):
    backend_logger.exception("Database operation failed: %s", exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


app.include_router(health.router)
app.include_router(reports.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(workflow.router, prefix=settings.api_prefix)
