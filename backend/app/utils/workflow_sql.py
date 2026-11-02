"""Numbered Jobs statements with typed values and SQL-free ORM hydration.

Callers own commits and rollbacks. Model changes are written explicitly through
catalog statements, then marked committed so ORM flushes cannot duplicate them.
"""
from sqlalchemy import Boolean, bindparam, inspect, text
from sqlalchemy.orm import make_transient_to_detached
from sqlalchemy.orm.attributes import set_committed_value

from app.models.workflow import Company, GeneratedFile, JobRun, ReportJob, UploadedQuery
from app.utils.query_store import query_store

GET_IDS = {Company: "8", ReportJob: "11", UploadedQuery: "12", JobRun: "18", GeneratedFile: "21"}
INSERT_IDS = {UploadedQuery: "13", ReportJob: "14", JobRun: "19", GeneratedFile: "22"}
READ_DEFAULTS = {
    "8": {"record_id": None, "filter_company_ids": False, "company_ids": ()},
    "10": {"client_id": None, "company_id": None},
    "11": {"record_id": None},
    "18": {"record_id": None, "failed_before": None, "statuses": ("Failed", "Partially Completed")},
    "21": {"record_id": None, "run_id": None},
}
READ_EXPANDING = {"8": ("company_ids",), "18": ("statuses",)}
JOB_FIELDS = (
    "title", "display_name", "company_id", "source_type", "source_key", "uploaded_query_id",
    "column_mappings", "delimiter", "schedule_time", "schedule_at", "recurrence", "day_of_week",
    "day_of_month", "recipients", "client_selections", "export_split_by", "report_options", "enabled", "next_run_at",
)
RUN_FIELDS = ("status", "current_step", "error_message", "step_log", "csv_content", "output_manifest", "completed_at")


def command(query_id, parameters=None, *, model=None, expanding=(), dialect=None):
    statement = text(query_store.get(query_id, dialect=dialect))
    for name in parameters or {}:
        column = None
        if model is not None:
            column = model.__table__.c.get("id" if name == "record_id" else name)
            if name == "company_ids": column = Company.__table__.c.id
            if name == "company_id": column = Company.__table__.c.id
            if name == "statuses": column = JobRun.__table__.c.status
            if name == "failed_before": column = JobRun.__table__.c.started_at
        value_type = column.type if column is not None else None
        if name == "filter_company_ids": value_type = Boolean()
        statement = statement.bindparams(bindparam(name, type_=value_type, expanding=name in expanding))
    return statement


def hydrate(db, model, row, *, overwrite=False):
    existing = db.identity_map.get(db.identity_key(model, row["id"]))
    if existing is not None:
        state = inspect(existing)
        for field, value in row.items():
            if overwrite or field in state.expired_attributes or field not in state.dict:
                set_committed_value(existing, field, value)
        return existing
    record = model(**dict(row))
    make_transient_to_detached(record)
    return db.merge(record, load=False)


def records(db, model, query_id, parameters=None, *, expanding=(), overwrite=False):
    parameters = {**READ_DEFAULTS.get(str(query_id), {}), **(parameters or {})}
    expanding = set(expanding) | set(READ_EXPANDING.get(str(query_id), ()))
    statement = command(query_id, parameters, model=model, expanding=expanding)
    # Match by column name: deployed tables can have a different column order.
    statement = statement.columns(**{column.key: column.type for column in model.__table__.columns})
    rows = db.execute(statement, parameters or {}).mappings().all()
    return [hydrate(db, model, row, overwrite=overwrite) for row in rows]


def one(db, model, query_id, parameters=None, *, overwrite=False):
    if parameters and any(value is None for key, value in parameters.items() if key in {"record_id", "run_id"}):
        return None
    rows = records(db, model, query_id, parameters, overwrite=overwrite)
    return rows[0] if rows else None


def identity(record):
    return inspect(record).identity[0]


def get(db, model, record_id):
    return one(db, model, GET_IDS[model], {"record_id": record_id})


def refresh(db, record):
    model = type(record)
    return one(db, model, GET_IDS[model], {"record_id": identity(record)}, overwrite=True)


def insert(db, record):
    model = type(record)
    query_id = INSERT_IDS[model]
    dialect = db.bind.dialect.name
    statement = text(query_store.get(query_id, dialect=dialect))
    # Each full INSERT defines its own bound fields; omitted columns retain defaults.
    parameters = {name: inspect(record).dict.get(name) for name in statement.compile().params}
    result = db.execute(command(query_id, parameters, model=model, dialect=dialect), parameters)
    record_id = result.scalar_one() if db.bind.dialect.name == "mssql" else result.lastrowid
    return get(db, model, record_id)


def update(db, record, query_id, fields):
    state = inspect(record)
    if not any(state.attrs[field].history.has_changes() for field in fields):
        return record
    parameters = {field: getattr(record, field) for field in fields}
    parameters["record_id"] = identity(record)
    db.execute(command(query_id, parameters, model=type(record)), parameters)
    return refresh(db, record)
