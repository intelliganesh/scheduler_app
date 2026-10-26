import csv
import io
import json
import re
from decimal import Decimal
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.workflow import Company, Employee, GeneratedFile, JobRun, Payroll, ReportJob, SampleSale, UploadedQuery
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.workflow import JobCreate

APPROVED_PROCEDURES = {
    "mapped_employee_payroll_report": "Mapped Employee Payroll Report",
    "employee_payroll_report": "Employee Payroll Report",
    "monthly_payroll_summary": "Monthly Payroll Summary",
    "department_payroll_report": "Department-wise Payroll Report",
    "employee_salary_breakdown": "Employee Salary Breakdown",
    "company_payroll_report": "Company Payroll Report",
}
MAPPING_FIELDS = (
    "employee_code", "employee_name", "department", "designation", "payroll_month",
    "basic_salary", "allowances", "deductions", "net_salary", "payment_status",
)
MAPPING_PROCEDURE = "mapped_employee_payroll_report"
LEGACY_PROCEDURES = {"sales_by_company": "dbo.usp_SalesByCompany", "monthly_sales_summary": "dbo.usp_MonthlySalesSummary", "product_sales_report": "dbo.usp_ProductSalesReport"}
APPROVED_TXT_QUERY = "SELECT e.employee_code AS employee_id, e.employee_name, e.department, e.designation, p.payroll_month, p.basic_salary, p.allowances, p.deductions, p.net_salary, p.payment_status FROM employees e JOIN payroll p ON p.employee_id = e.id WHERE e.company_id = :company_id AND p.payroll_month = (SELECT MAX(p2.payroll_month) FROM payroll p2 JOIN employees e2 ON e2.id = p2.employee_id WHERE e2.company_id = :company_id) ORDER BY e.employee_code"


class WorkflowService:
    def __init__(self, repository: WorkflowRepository | None = None): self.repository = repository or WorkflowRepository()

    def seed(self, db: Session) -> None:
        companies = db.query(Company).order_by(Company.id).all()
        if not companies:
            companies = [Company(company_name=name) for name in ("Company A", "Company B", "Company C")]
            db.add_all(companies); db.flush()
            # Keep the original sample rows intact for existing historical jobs.
            now = datetime.now()
            for company in companies:
                for index, product in enumerate(("Widget", "Gadget", "Service"), start=1):
                    db.add(SampleSale(company_id=company.id, product_name=product, quantity=index * 4, amount=float(index * 125.5), sale_date=now))
            db.commit()
        self.seed_payroll(db, companies)

    def seed_payroll(self, db: Session, companies: list[Company]) -> None:
        if db.query(Employee).count(): return
        departments = (("Finance", "Payroll Analyst"), ("Operations", "Operations Specialist"), ("Technology", "Systems Analyst"), ("People", "People Coordinator"), ("Sales", "Account Specialist"))
        names = ("Avery Morgan", "Jordan Ellis", "Riley Hart", "Casey Rowan", "Taylor Quinn", "Morgan Reed", "Cameron Blake", "Jamie Vale", "Drew Parker", "Skyler Lane", "Emery Stone", "Robin Avery")
        current_month = datetime(datetime.now().year, datetime.now().month, 1)
        months = [(current_month - timedelta(days=32 * offset)).replace(day=1) for offset in (2, 1, 0)]
        for company_index, company in enumerate(companies, start=1):
            for index in range(12):
                department, designation = departments[index % len(departments)]
                employee = Employee(employee_code=f"D{company_index:02d}-{index + 1:04d}", employee_name=names[(company_index * 12 + index) % len(names)], company_id=company.id, department=department, designation=designation, is_active=True)
                db.add(employee); db.flush()
                for month_index, month in enumerate(months):
                    basic = Decimal(4200 + company_index * 275 + index * 85 + month_index * 20)
                    allowance = (basic * Decimal("0.12")).quantize(Decimal("0.01")); deduction = (basic * Decimal("0.07")).quantize(Decimal("0.01"))
                    db.add(Payroll(employee_id=employee.id, payroll_month=month, basic_salary=basic, allowances=allowance, deductions=deduction, net_salary=basic + allowance - deduction, payment_status="Paid" if month_index < 2 else "Processing"))
        db.commit()

    def create_upload(self, db: Session, original_name: str, content: bytes) -> UploadedQuery:
        settings = get_settings()
        if not original_name.lower().endswith(".txt") or len(content) > settings.max_upload_bytes:
            raise ValueError("Upload must be a TXT file within the configured size limit.")
        try:
            query = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("TXT uploads must use UTF-8 encoding.") from exc
        # Keep the original approved TXT-query workflow available for existing users.
        if self._normalize(query) == self._normalize(APPROVED_TXT_QUERY):
            folder = Path(settings.uploads_dir); folder.mkdir(parents=True, exist_ok=True)
            stored_name = f"{uuid4().hex}.txt"; (folder / stored_name).write_text(query.strip(), encoding="utf-8")
            record = UploadedQuery(original_name=original_name, stored_name=stored_name, approved_key="employee_payroll_report", column_names=None)
            db.add(record); db.commit(); db.refresh(record); return record
        names = [line.strip() for line in query.splitlines()]
        if not names or any(not name for name in names):
            raise ValueError("TXT uploads must contain one non-blank column name per line.")
        if len(names) > len(MAPPING_FIELDS):
            raise ValueError("TXT uploads contain too many columns for the approved payroll report.")
        if any(len(name) > 160 or any(ord(char) < 32 for char in name) for name in names):
            raise ValueError("TXT column names contain invalid characters or are too long.")
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError("TXT column names must be unique.")
        folder = Path(settings.uploads_dir); folder.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid4().hex}.txt"; (folder / stored_name).write_text("\n".join(names) + "\n", encoding="utf-8")
        record = UploadedQuery(original_name=original_name, stored_name=stored_name, approved_key=MAPPING_PROCEDURE, column_names=json.dumps(names, ensure_ascii=False))
        db.add(record); db.commit(); db.refresh(record); return record

    def create_job(self, db: Session, payload: JobCreate) -> ReportJob:
        if db.get(Company, payload.company_id) is None: raise ValueError("Company not found.")
        if payload.source_type == "procedure" and payload.source_key not in APPROVED_PROCEDURES: raise ValueError("Choose an approved stored procedure.")
        if payload.source_type == "txt" and not payload.uploaded_query_id: raise ValueError("Choose an approved TXT upload.")
        mappings = payload.column_mappings or []
        if payload.source_key == MAPPING_PROCEDURE:
            upload = self.repository.uploaded(db, payload.uploaded_query_id) if payload.uploaded_query_id else None
            if not upload or upload.approved_key != MAPPING_PROCEDURE:
                raise ValueError("Upload a valid TXT column list for the mapped payroll procedure.")
            names = json.loads(upload.column_names or "[]")
            if [item.display_name for item in mappings] != names:
                raise ValueError("Every TXT column must be mapped in its original order.")
            if any(item.database_field not in MAPPING_FIELDS for item in mappings):
                raise ValueError("Choose fields from the approved payroll field list.")
        elif mappings or payload.uploaded_query_id:
            raise ValueError("TXT mappings are supported only by the mapped payroll procedure.")
        values = payload.model_dump(exclude={"column_mappings"})
        values["recipients"] = json.dumps(payload.recipients, ensure_ascii=False) if payload.recipients else None
        values["column_mappings"] = json.dumps([item.model_dump() for item in mappings], ensure_ascii=False) if mappings else None
        values["schedule_time"] = payload.schedule_at.strftime("%H:%M"); values["recurrence"] = "once"; values["next_run_at"] = payload.schedule_at
        job = ReportJob(**values); db.add(job); db.commit(); db.refresh(job); return job

    def set_enabled(self, db: Session, job_id: int, enabled: bool) -> ReportJob:
        job = self.repository.job(db, job_id)
        if not job: raise ValueError("Job not found.")
        job.enabled = enabled; db.commit(); db.refresh(job); return job

    def run_job(self, db: Session, job_id: int, retry_run_id: int | None = None) -> JobRun:
        job = self.repository.job(db, job_id)
        if not job: raise ValueError("Job not found.")
        run = self.repository.run(db, retry_run_id) if retry_run_id else None
        if run and run.status not in {"Failed", "Partially Completed"}: raise ValueError("Only failed runs can be retried.")
        is_new = run is None
        if is_new:
            run = JobRun(job_id=job.id, status="Running", current_step="SQL execution", step_log="[]")
            db.add(run); db.commit(); db.refresh(run)
        if not is_new and run.status == "Running": raise ValueError("This run is already active.")
        run.status = "Running"; run.error_message = None
        try:
            if not run.csv_content:
                rows, headers = self._execute_source(db, job)
                self._log(run, "SQL execution", "Completed")
                run.current_step = "CSV generation"
                run.csv_content = self._csv(headers, rows)
                self._log(run, "CSV generation", "Completed")
            run.current_step = "File storage"
            generated = self._store_file(db, job, run)
            self._log(run, "File storage", "Completed")
            run.status = "Completed"; run.current_step = "Completed"; run.completed_at = datetime.now(); job.last_run_status = run.status
            db.commit(); db.refresh(run); return run
        except Exception as exc:
            run.status = "Failed" if not run.csv_content else "Partially Completed"; run.error_message = "Report execution failed. Review the run details."
            run.current_step = run.current_step or "Unknown"; self._log(run, run.current_step, "Failed")
            job.last_run_status = run.status; db.commit(); raise ValueError(run.error_message) from exc

    def _execute_source(self, db: Session, job: ReportJob):
        dialect = db.bind.dialect.name
        if job.source_key == MAPPING_PROCEDURE:
            mappings = json.loads(job.column_mappings or "[]")
            if dialect == "mssql":
                result = db.execute(text("EXEC dbo.usp_GenerateMappedPayrollReport @company_id=:company_id, @column_mappings=:column_mappings"), {"company_id": job.company_id, "column_mappings": json.dumps(mappings, ensure_ascii=False)})
            else:
                expressions = {
                    "employee_code": "e.employee_code", "employee_name": "e.employee_name", "department": "e.department",
                    "designation": "e.designation", "payroll_month": "p.payroll_month", "basic_salary": "p.basic_salary",
                    "allowances": "p.allowances", "deductions": "p.deductions", "net_salary": "p.net_salary", "payment_status": "p.payment_status",
                }
                select_list = ", ".join(f'{expressions[item["database_field"]]} AS "{item["display_name"].replace(chr(34), chr(34) * 2)}"' for item in mappings)
                result = db.execute(text(f"SELECT {select_list} FROM employees e JOIN payroll p ON p.employee_id=e.id WHERE e.company_id=:company_id ORDER BY e.employee_code, p.payroll_month DESC"), {"company_id": job.company_id})
            rows = result.fetchmany(get_settings().max_report_rows)
            return [tuple(row) for row in rows], list(result.keys())
        if job.source_type == "procedure" and dialect == "mssql":
            names = {"employee_payroll_report": "dbo.usp_EmployeePayrollReport", "monthly_payroll_summary": "dbo.usp_MonthlyPayrollSummary", "department_payroll_report": "dbo.usp_DepartmentPayrollReport", "employee_salary_breakdown": "dbo.usp_EmployeeSalaryBreakdown", "company_payroll_report": "dbo.usp_CompanyPayrollReport", **LEGACY_PROCEDURES}
            result = db.execute(text(f"EXEC {names[job.source_key]} @company_id=:company_id"), {"company_id": job.company_id})
        elif job.source_type == "procedure" and job.source_key in APPROVED_PROCEDURES:
            result = db.execute(text(APPROVED_TXT_QUERY), {"company_id": job.company_id})
        elif job.source_type == "txt":
            result = db.execute(text(APPROVED_TXT_QUERY), {"company_id": job.company_id})
        else:
            result = db.execute(text("SELECT product_name, quantity, amount, sale_date FROM sample_sales WHERE company_id = :company_id ORDER BY sale_date DESC"), {"company_id": job.company_id})
        rows = result.fetchmany(get_settings().max_report_rows)
        return [tuple(row) for row in rows], list(result.keys())

    def _store_file(self, db: Session, job: ReportJob, run: JobRun) -> GeneratedFile:
        existing = db.query(GeneratedFile).filter_by(run_id=run.id).first()
        if existing: return existing
        company = db.get(Company, job.company_id)
        folder = Path(get_settings().generated_reports_dir); folder.mkdir(parents=True, exist_ok=True)
        filename = f"{company.company_name.lower().replace(' ', '_')}_{job.id}_run_{run.id}_{datetime.now():%Y%m%d_%H%M%S}.csv"
        path = folder / filename; path.write_text(run.csv_content or "", encoding="utf-8", newline="")
        generated = GeneratedFile(run_id=run.id, job_id=job.id, company_id=job.company_id, file_name=filename, storage_path=str(path.resolve()), row_count=max(0, len((run.csv_content or "").splitlines()) - 1), file_size=path.stat().st_size)
        db.add(generated); return generated

    @staticmethod
    def _normalize(query: str) -> str: return re.sub(r"\s+", " ", query.strip()).lower()
    @staticmethod
    def _safe(value): return "'" + value if isinstance(value, str) and value[:1] in ("=", "+", "-", "@") else value
    def _csv(self, headers, rows):
        output = io.StringIO(); writer = csv.writer(output); writer.writerow(headers); writer.writerows([[self._safe(v) for v in row] for row in rows]); return output.getvalue()
    @staticmethod
    def _log(run, step, state):
        history = json.loads(run.step_log or "[]"); history.append({"step": step, "status": state, "at": datetime.now().isoformat()}); run.step_log = json.dumps(history)
