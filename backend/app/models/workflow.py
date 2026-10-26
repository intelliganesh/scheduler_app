from datetime import datetime

from decimal import Decimal
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, Unicode, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_name: Mapped[str] = mapped_column(String(120), unique=True, index=True)


class SampleSale(Base):
    __tablename__ = "sample_sales"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[int] = mapped_column(Integer)
    amount: Mapped[float] = mapped_column(nullable=False)
    sale_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    employee_name: Mapped[str] = mapped_column(Unicode(160))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    department: Mapped[str] = mapped_column(Unicode(100))
    designation: Mapped[str] = mapped_column(Unicode(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class Payroll(Base):
    __tablename__ = "payroll"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    payroll_month: Mapped[datetime] = mapped_column(DateTime, index=True)
    basic_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    allowances: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    deductions: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    net_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_status: Mapped[str] = mapped_column(String(30), nullable=False)
    __table_args__ = (Index("ix_payroll_employee_month", "employee_id", "payroll_month", unique=True),)


class UploadedQuery(Base):
    __tablename__ = "uploaded_queries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    approved_key: Mapped[str] = mapped_column(String(80))
    column_names: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ReportJob(Base):
    __tablename__ = "report_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(160), index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(20))  # procedure or txt
    source_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    uploaded_query_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_queries.id"), nullable=True)
    column_mappings: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule_time: Mapped[str] = mapped_column(String(5))  # HH:MM, Asia/Kolkata
    schedule_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recurrence: Mapped[str] = mapped_column(String(12))
    day_of_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recipients: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class JobRun(Base):
    __tablename__ = "job_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("report_jobs.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="Pending")
    current_step: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_log: Mapped[str] = mapped_column(Text, default="[]")
    csv_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class GeneratedFile(Base):
    __tablename__ = "generated_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("job_runs.id"), unique=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("report_jobs.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(255), unique=True)
    storage_path: Mapped[str] = mapped_column(String(500))
    row_count: Mapped[int] = mapped_column(Integer)
    file_size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
