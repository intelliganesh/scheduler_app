from datetime import datetime
import json
import re

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config.settings import get_settings

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def normalize_recipients(value) -> list[str]:
    """Accept new lists and legacy scalar/JSON values, returning clean emails."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = text.split(",")
        value = decoded if isinstance(decoded, list) else [decoded]
    if not isinstance(value, list):
        raise ValueError("Email recipients must be a list of email addresses.")
    if len(value) > get_settings().max_email_recipients:
        raise ValueError(f"You can add at most {get_settings().max_email_recipients} email recipients.")
    recipients: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError("Email recipients must be strings.")
        email = item.strip()
        if not EMAIL_PATTERN.fullmatch(email):
            raise ValueError(f"Invalid email address: {email or '(empty)'}")
        key = email.casefold()
        if key in seen:
            raise ValueError("Email recipients must be unique.")
        seen.add(key)
        recipients.append(email)
    return recipients


class ColumnMapping(BaseModel):
    display_name: str = Field(min_length=1, max_length=160)
    database_field: str = Field(min_length=1, max_length=80)


class ProcedureRead(BaseModel):
    key: str
    name: str
    supports_mapping: bool = False
    allowed_fields: list[str] = []


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=160)
    company_id: int
    source_type: str
    source_key: str | None = None
    uploaded_query_id: int | None = None
    schedule_at: datetime
    recipients: list[str] = Field(default_factory=list)
    column_mappings: list[ColumnMapping] | None = None
    enabled: bool = True

    @field_validator("source_type")
    @classmethod
    def source(cls, value: str) -> str:
        if value not in {"procedure", "txt"}:
            raise ValueError("source_type must be procedure or txt")
        return value

    @field_validator("recipients", mode="before")
    @classmethod
    def validate_recipients(cls, value):
        return normalize_recipients(value)

    @model_validator(mode="after")
    def validate_mapping(self):
        if self.column_mappings:
            if len({item.display_name.casefold() for item in self.column_mappings}) != len(self.column_mappings):
                raise ValueError("TXT column names must be unique.")
            if len({item.database_field for item in self.column_mappings}) != len(self.column_mappings):
                raise ValueError("Database fields must be mapped one-to-one.")
        return self


class JobRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str
    display_name: str
    company_id: int
    source_type: str
    source_key: str | None
    uploaded_query_id: int | None
    column_mappings: str | None
    schedule_time: str
    schedule_at: datetime | None
    recurrence: str
    day_of_week: int | None
    day_of_month: int | None
    recipients: list[str] = Field(default_factory=list)
    enabled: bool
    next_run_at: datetime | None
    last_run_status: str | None
    created_at: datetime | None

    @field_validator("recipients", mode="before")
    @classmethod
    def validate_existing_recipients(cls, value):
        return normalize_recipients(value)



class RunRead(BaseModel):
    id: int
    job_id: int
    status: str
    current_step: str | None
    error_message: str | None
    step_log: str
    started_at: datetime
    completed_at: datetime | None

    class Config:
        from_attributes = True
