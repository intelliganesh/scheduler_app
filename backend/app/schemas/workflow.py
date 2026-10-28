from datetime import datetime
from decimal import Decimal
import json
import re

from typing import Literal

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


def normalize_client_selections(value) -> dict[str, list[str]]:
    """Normalize per-company manual emails while accepting legacy numeric IDs."""
    if value is None or value == "":
        return {}
    if not isinstance(value, dict):
        raise ValueError("Client selections must be an object keyed by company ID.")
    selections: dict[str, list[str]] = {}
    for raw_company_id, raw_values in value.items():
        try:
            company_id = str(int(raw_company_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("Client selection is invalid.") from exc
        if raw_values is None:
            raw_values = []
        if not isinstance(raw_values, list):
            raise ValueError("Each company must have a list of email addresses.")
        if len(raw_values) > get_settings().max_email_recipients:
            raise ValueError(f"You can add at most {get_settings().max_email_recipients} email recipients per company.")
        emails: list[str] = []
        seen: set[str] = set()
        for raw_email in raw_values:
            if not isinstance(raw_email, (str, int)):
                raise ValueError("Company email recipients must be strings.")
            email = str(raw_email).strip()
            # Numeric values are retained only for compatibility with earlier
            # jobs that stored ClientEmail IDs; new UI values are email strings.
            if not email.isdigit() and not EMAIL_PATTERN.fullmatch(email):
                raise ValueError(f"Invalid email address: {email or '(empty)'}")
            key = email.casefold()
            if key in seen:
                raise ValueError("Company email recipients must be unique.")
            seen.add(key)
            emails.append(email)
        selections[company_id] = emails
    return selections


class ColumnMapping(BaseModel):
    # display_name/database_field are retained for compatibility with existing jobs
    # and the SQL Server mapped-report procedure. New clients may use the clearer
    # column_name/db_column_name names instead.
    display_name: str | None = Field(default=None, max_length=160)
    database_field: str | list[str] | None = Field(default=None)
    column_name: str | None = Field(default=None, max_length=160)
    db_column_name: str | list[str] | None = Field(default=None)
    default_value: str | None = Field(default=None, max_length=500)
    record_type: Literal["H", "D", "T"] = "D"
    format: Literal["Default", "Text", "TextPhone", "PhoneDash", "PhoneParens", "Date", "DateDMY", "DateMDY", "CurrencyUSD", "CurrencyINR", "CurrencyEUR"] = "Default"
    format_pattern: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def normalize_mapping(self):
        column_name = (self.column_name or self.display_name or "").strip()
        raw_fields = self.db_column_name if self.db_column_name is not None else self.database_field
        fields = raw_fields if isinstance(raw_fields, list) else [raw_fields or ""]
        fields = [str(field).strip() for field in fields if str(field).strip()]
        if not column_name:
            raise ValueError("Each mapping needs a column name.")
        if self.default_value is not None and fields:
            raise ValueError("A mapping can use either a database field or a default value, not both.")
        object.__setattr__(self, "column_name", column_name)
        object.__setattr__(self, "display_name", self.display_name or column_name)
        object.__setattr__(self, "db_column_name", fields)
        object.__setattr__(self, "database_field", fields)
        return self


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
    source_key: str | None = "company_payroll_report"
    uploaded_query_id: int | None = None
    schedule_at: datetime
    recipients: list[str] = Field(default_factory=list)
    column_mappings: list[ColumnMapping] | None = None
    delimiter: Literal[",", "|", ";", "\t"] = ","
    client_selections: dict[str, list[str]] = Field(default_factory=dict)
    export_split_by: Literal["file_name", "client_id", "pay_date", "file_client", "file_pay", "client_pay", "file_client_pay"] = "file_name"
    sort_field: str | None = Field(default=None, max_length=80)
    sort_direction: Literal["asc", "desc"] = "asc"
    filter_field: str | None = Field(default=None, max_length=80)
    filter_operator: Literal["eq", "gt", "gte", "lt", "lte"] = "gt"
    filter_value: Decimal | None = None
    sort_rules: list[dict] = Field(default_factory=list)
    filter_rules: list[dict] = Field(default_factory=list)
    schedule_type: Literal["one_time", "every_2_minutes", "hourly_1", "hourly_2", "hourly_4", "daily", "weekly", "monthly"] = "one_time"
    weekly_day: int | None = Field(default=None, ge=0, le=6)
    monthly_day: int | None = Field(default=None, ge=1, le=31)
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

    @field_validator("client_selections", mode="before")
    @classmethod
    def validate_client_selections(cls, value):
        return normalize_client_selections(value)

    @model_validator(mode="after")
    def validate_mapping(self):
        if self.column_mappings:
            if len({item.column_name.casefold() for item in self.column_mappings}) != len(self.column_mappings):
                raise ValueError("TXT column names must be unique.")
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
    delimiter: str | None
    client_selections: dict[str, list[str]] = Field(default_factory=dict)
    export_split_by: str | None
    report_options: dict = Field(default_factory=dict)
    schedule_type: str
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
    updated_at: datetime | None

    @field_validator("report_options", mode="before")
    @classmethod
    def validate_report_options(cls, value):
        if value is None or value == "": return {}
        if isinstance(value, dict): return value
        try: return json.loads(value)
        except (TypeError, json.JSONDecodeError): return {}

    @field_validator("recipients", mode="before")
    @classmethod
    def validate_existing_recipients(cls, value):
        return normalize_recipients(value)

    @field_validator("client_selections", mode="before")
    @classmethod
    def normalize_client_selections(cls, value):
        if value is None or value == "": return {}
        if isinstance(value, str):
            try: value = json.loads(value)
            except json.JSONDecodeError: return {}
        if not isinstance(value, dict): return {}
        return {str(client_id): [str(email_id) for email_id in (email_ids or [])] for client_id, email_ids in value.items()}



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
