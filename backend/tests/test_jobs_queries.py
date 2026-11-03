"""Jobs-screen SQL regression tests with isolated rows and file storage."""
import io
import json
import csv
import zipfile
import os
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import Workbook
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.sql.selectable import TextualSelect

from app.config.settings import Settings, get_settings
from app.controllers.workflow_controller import WorkflowController
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models.workflow import Company, GeneratedFile, JobRun, ReportJob, UploadedQuery
from app.schemas.workflow import JobCreate
from app.services.scheduler_service import SchedulerService
from app.services.workflow_service import KOLKATA, WorkflowService
from app.utils.security import create_access_token
from app.utils.query_store import query_store
from app.utils.workflow_sql import get, records, refresh, update


class JobsQueryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False)
        self.db = self.Session()
        self.addCleanup(self.db.close)
        self.service = WorkflowService()
        self.service.seed(self.db)
        settings = Settings(_env_file=None, generated_reports_dir=f"{self.folder.name}/reports", uploads_dir=f"{self.folder.name}/uploads")
        patcher = patch("app.services.workflow_service.get_settings", return_value=settings)
        patcher.start(); self.addCleanup(patcher.stop)
        self.statements = []
        event.listen(self.engine, "before_cursor_execute", self.capture)

    def capture(self, connection, cursor, sql, params, context, many):
        self.statements.append(context.compiled.statement if context.compiled else None)

    def assert_catalog_only(self):
        self.assertTrue(self.statements)
        self.assertTrue(all(isinstance(statement, (TextClause, TextualSelect)) for statement in self.statements),
                        [type(statement).__name__ for statement in self.statements])
        self.assertFalse(self.db.new)
        self.assertFalse(self.db.dirty)

    def payload(self, **overrides):
        values = dict(title="Jobs SQL regression", display_name="Payroll", company_id=1,
                      source_type="procedure", source_key="company_payroll_report",
                      schedule_at=datetime.now(KOLKATA) + timedelta(days=2), schedule_type="daily")
        values.update(overrides)
        return JobCreate(**values)

    def test_lookup_create_edit_enable_and_identity(self):
        repository = self.service.repository
        self.assertEqual(len(repository.companies(self.db)), 3)
        self.assertEqual(len(repository.clients(self.db, 1)), 3)
        self.assertEqual(len(repository.client_emails(self.db, 1)), 2)
        self.assertEqual(len(repository.company_emails(self.db, 1)), 6)
        payload = self.payload()
        job = self.service.create_job(self.db, payload)
        job_id, created_at = job.id, job.created_at
        self.assertIsInstance(job.created_at, datetime)
        self.assertIsInstance(job.updated_at, datetime)
        self.assertIs(repository.job(self.db, job_id), job)
        self.assertEqual(repository.jobs(self.db)[0].id, job_id)
        edited = self.service.update_job(self.db, job_id, payload.model_copy(update={"title": "Changed title", "schedule_type": "weekly", "weekly_day": 2}))
        self.assertIs(edited, job)
        self.assertEqual(edited.title, "Changed title")
        self.assertEqual(edited.recurrence, "weekly")
        self.assertEqual(edited.day_of_week, 2)
        self.assertEqual(edited.created_at, created_at)
        self.assertFalse(self.service.set_enabled(self.db, job_id, False).enabled)
        self.assertTrue(self.service.set_enabled(self.db, job_id, True).enabled)
        self.assert_catalog_only()

    def test_unchanged_configuration_skips_update(self):
        payload = self.payload()
        job = self.service.create_job(self.db, payload)
        original_timestamp = job.updated_at
        self.service.update_job(self.db, job.id, payload)
        self.assertEqual(job.updated_at, original_timestamp)
        self.assert_catalog_only()

    def test_run_history_file_storage_and_download_lookup(self):
        job_id = self.service.create_job(self.db, self.payload()).id
        run = self.service.run_job(self.db, job_id)
        self.assertEqual(run.status, "Completed")
        self.assertIsInstance(run.started_at, datetime)
        self.assertTrue(run.csv_content)
        generated = self.service.repository.files(self.db)[0]
        self.assertEqual(generated.run_id, run.id)
        self.assertGreater(generated.row_count, 0)
        self.assertTrue(Path(generated.storage_path).is_file())
        self.assertIs(self.service.repository.file(self.db, generated.id), generated)
        self.assertEqual(self.service.repository.runs(self.db)[0].id, run.id)
        self.assertEqual(self.service.repository.runs(self.db, datetime(2100, 1, 1)), [])
        self.assert_catalog_only()

    def test_failed_run_retry_and_failure_cutoff(self):
        job_id = self.service.create_job(self.db, self.payload()).id
        with patch.object(self.service, "_execute_source", side_effect=ValueError("Controlled report failure")):
            with self.assertRaisesRegex(ValueError, "Controlled report failure"):
                self.service.run_job(self.db, job_id)
        failed = self.service.repository.runs(self.db, datetime(2100, 1, 1))[0]
        run_id = failed.id
        self.assertEqual(failed.status, "Failed")
        retried = self.service.run_job(self.db, job_id, run_id)
        self.assertEqual(retried.id, run_id)
        self.assertEqual(retried.status, "Completed")
        self.assertIsNone(retried.error_message)
        self.assert_catalog_only()

    def test_txt_and_excel_upload_metadata(self):
        uploaded = self.service.create_upload(self.db, "columns.txt", b"Employee\nSalary")
        self.assertEqual(json.loads(uploaded.column_names), ["Employee", "Salary"])
        self.assertIs(self.service.repository.uploaded(self.db, uploaded.id), uploaded)
        book = Workbook(); sheet = book.active
        sheet.append(["record type", "column name"]); sheet.append(["D", "Employee"])
        buffer = io.BytesIO(); book.save(buffer); book.close()
        excel = self.service.create_upload(self.db, "columns.xlsx", buffer.getvalue())
        self.assertEqual(json.loads(excel.column_names)[0]["column_name"], "Employee")
        self.assertIsInstance(excel.created_at, datetime)
        self.assert_catalog_only()

    def test_mapped_report_filters_sort_and_bound_values(self):
        uploaded_id = self.service.create_upload(self.db, "columns.txt", b"Employee\nSalary").id
        payload = self.payload(source_key="mapped_employee_payroll_report", uploaded_query_id=uploaded_id,
                               client_selections={"1": []},
                               column_mappings=[{"column_name": "Employee", "db_column_name": ["employee_name"]},
                                                {"column_name": "Salary", "db_column_name": ["net_salary"]}],
                               filter_rules=[{"field": "department", "operator": "in", "value": ["Finance", "Technology"]}],
                               sort_rules=[{"field": "net_salary", "direction": "desc"}])
        job = self.service.create_job(self.db, payload)
        rows, _ = self.service._query_application_rows(self.db, job)
        self.assertTrue(rows)
        self.assertTrue(all(row["__client_id"] == 1 for row in rows))
        values = [row["__net_salary"] for row in rows]
        self.assertEqual(values, sorted(values, reverse=True))
        job_id = job.id
        malicious = payload.model_copy(update={"filter_rules": [{"field": "employee_name", "operator": "eq", "value": "' OR 1=1 --"}]})
        job = self.service.update_job(self.db, job_id, malicious)
        self.assertEqual(self.service._query_application_rows(self.db, job)[0], [])
        self.assert_catalog_only()

    def test_controller_and_background_schedule_updates(self):
        controller = WorkflowController(self.service)
        next_time = datetime(2030, 1, 2, 10, 0)
        scheduler = SimpleNamespace(scheduler=SimpleNamespace(running=True), sync_job=lambda job: setattr(job, "next_run_at", next_time))
        with patch("app.controllers.workflow_controller.get_scheduler", return_value=scheduler):
            job = controller.create_job(self.db, self.payload())
        job_id = job.id
        self.assertEqual(job.next_run_at, next_time)
        background = SchedulerService()
        with patch("app.services.scheduler_service.SessionLocal", self.Session), patch.object(background, "sync_job", side_effect=lambda record: setattr(record, "next_run_at", datetime(2031, 1, 1))):
            background.sync_all()
        refresh(self.db, job)
        self.assertEqual(job.next_run_at, datetime(2031, 1, 1))
        with patch("app.services.scheduler_service.SessionLocal", self.Session), patch.object(background.scheduler, "get_job", return_value=SimpleNamespace(next_run_time=next_time)):
            background._run(job_id)
        refresh(self.db, job)
        self.assertEqual(job.last_run_status, "Completed")
        self.assertEqual(job.next_run_at, next_time)
        self.assert_catalog_only()

    def test_jobs_http_endpoints_keep_response_shapes(self):
        def session():
            db = self.Session()
            try: yield db
            finally: db.close()
        app.dependency_overrides[get_db] = session
        self.addCleanup(app.dependency_overrides.clear)
        token = create_access_token("jobs-test", ["jobs", "generated_files"], [])
        headers = {"Authorization": f"Bearer {token}"}
        client = TestClient(app)
        created = client.post("/api/jobs", json=json.loads(self.payload().model_dump_json()), headers=headers)
        self.assertEqual(created.status_code, 200, created.text)
        job_id = created.json()["id"]
        listed = client.get("/api/jobs", headers=headers)
        self.assertEqual(listed.json()[0]["id"], job_id)
        toggled = client.post(f"/api/jobs/{job_id}/enabled?enabled=false", headers=headers)
        self.assertIs(toggled.json()["enabled"], False)
        self.assertEqual(client.get("/api/runs", headers=headers).json(), [])
        self.assertEqual(client.get("/api/files", headers=headers).json(), [])
        self.assert_catalog_only()

    def test_two_hour_schedule_api_persistence_reload_and_execution(self):
        def session():
            db = self.Session()
            try: yield db
            finally: db.close()
        app.dependency_overrides[get_db] = session
        self.addCleanup(app.dependency_overrides.clear)
        background = SchedulerService()
        background.scheduler.start(paused=True)
        self.addCleanup(background.stop)
        start = (datetime.now(KOLKATA) + timedelta(days=2)).replace(second=0, microsecond=0)
        headers = {"Authorization": f"Bearer {create_access_token('jobs-test', ['jobs', 'generated_files'], [])}"}
        client = TestClient(app)
        with patch("app.controllers.workflow_controller.get_scheduler", return_value=background), patch("app.services.scheduler_service.SessionLocal", self.Session):
            payload = self.payload(schedule_type="hourly_2", schedule_at=start)
            created = client.post("/api/jobs", json=json.loads(payload.model_dump_json()), headers=headers)
            self.assertEqual(created.status_code, 200, created.text)
            job_id = created.json()["id"]
            self.assertEqual(created.json()["schedule_type"], "hourly_2")
            scheduled = background.scheduler.get_job(f"report-job-{job_id}")
            self.assertEqual(scheduled.trigger.interval, timedelta(hours=2))
            self.assertEqual(scheduled.next_run_time, start)
            # Reload from committed database records, as at application startup.
            background.scheduler.remove_all_jobs()
            background.sync_all()
            scheduled = background.scheduler.get_job(f"report-job-{job_id}")
            first = scheduled.next_run_time
            for _ in range(13):
                following = scheduled.trigger.get_next_fire_time(first, first)
                self.assertEqual(following - first, timedelta(hours=2))
                first = following
            # Exercise the actual registered callback without waiting two hours.
            scheduled.func(*scheduled.args)
            runs = self.service.repository.runs(self.db)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].status, "Completed")
            self.assertTrue(Path(self.service.repository.files(self.db)[0].storage_path).is_file())
            toggled = client.post(f"/api/jobs/{job_id}/enabled?enabled=false", headers=headers)
            self.assertEqual(toggled.status_code, 200, toggled.text)
            self.assertIsNone(background.scheduler.get_job(f"report-job-{job_id}"))
            toggled = client.post(f"/api/jobs/{job_id}/enabled?enabled=true", headers=headers)
            self.assertEqual(toggled.status_code, 200, toggled.text)
            self.assertEqual(background.scheduler.get_job(f"report-job-{job_id}").trigger.interval, timedelta(hours=2))
        self.assert_catalog_only()

    def test_two_hour_schedule_restart_after_missed_run_keeps_original_alignment(self):
        start = datetime(2026, 11, 2, 23, 30, tzinfo=KOLKATA)
        trigger = SchedulerService.build_trigger(SimpleNamespace(recurrence="hourly_2", schedule_at=start.replace(tzinfo=None)))
        now = start + timedelta(hours=5, minutes=10)
        next_run = trigger.get_next_fire_time(None, now)
        self.assertEqual(next_run, start + timedelta(hours=6))
        self.assertEqual(next_run.strftime("%Y-%m-%d %H:%M"), "2026-11-03 05:30")

    def test_smtp_failure_preserves_report_and_retry_reuses_it(self):
        settings = Settings(_env_file=None, smtp_enabled=True, generated_reports_dir=f"{self.folder.name}/reports")
        job_id = self.service.create_job(self.db, self.payload(
            recipients=["finance@example.com"], client_selections={"1": ["Finance@example.com", "manager@example.com"]})).id
        with patch("app.services.workflow_service.get_settings", return_value=settings), patch("app.services.workflow_service.send_report", side_effect=ValueError("SMTP delivery failed")) as send:
            with self.assertRaisesRegex(ValueError, "Email delivery"):
                self.service.run_job(self.db, job_id)
            self.assertEqual(send.call_args.args[1], ["finance@example.com", "manager@example.com"])
        failed = self.service.repository.runs(self.db)[0]
        self.assertEqual(failed.status, "Partially Completed")
        generated = self.service.repository.files(self.db)[0]
        self.assertTrue(Path(generated.storage_path).is_file())
        storage_path = generated.storage_path
        with patch("app.services.workflow_service.get_settings", return_value=settings), patch("app.services.workflow_service.send_report", return_value=True) as send, patch.object(self.service, "_execute_source", side_effect=AssertionError("Must reuse output")):
            retried = self.service.run_job(self.db, job_id, failed.id)
            self.assertEqual(retried.status, "Completed")
            self.assertEqual(send.call_args.args[2], storage_path)
        self.assertEqual(len(self.service.repository.files(self.db)), 1)
        self.assert_catalog_only()

    def test_smtp_legacy_recipient_ids_are_scoped_to_company(self):
        job = self.service.create_job(self.db, self.payload(client_selections={"1": ["1"]}))
        expected = self.service.repository.company_emails(self.db, 1)[0].email
        self.assertEqual(self.service._email_recipients(self.db, job), [expected])
        job.client_selections = json.dumps({"2": ["1"]})
        with self.assertRaisesRegex(ValueError, "no longer belongs"):
            self.service._email_recipients(self.db, job)

    def test_unsupported_sources_do_not_execute_removed_sample_sales_query(self):
        job = self.service.create_job(self.db, self.payload())
        # A historical source is not offered by the current Jobs form.
        with self.assertRaisesRegex(ValueError, "Unsupported report source"):
            self.service._execute_source(self.db, SimpleNamespace(source_key="historical", source_type="historical"))
        self.assert_catalog_only()



    def test_partial_run_retry_reuses_existing_report_output(self):
        job_id = self.service.create_job(self.db, self.payload()).id
        with patch.object(self.service, "_store_file", side_effect=OSError("Controlled storage failure")):
            with self.assertRaisesRegex(ValueError, "File storage"):
                self.service.run_job(self.db, job_id)
        partial = self.service.repository.runs(self.db)[0]
        run_id, original_csv = partial.id, partial.csv_content
        self.assertEqual(partial.status, "Partially Completed")
        with patch.object(self.service, "_execute_source", side_effect=AssertionError("Output should be reused")):
            retried = self.service.run_job(self.db, job_id, run_id)
        self.assertEqual(retried.status, "Completed")
        self.assertEqual(retried.csv_content, original_csv)
        self.assertEqual(len(self.service.repository.files(self.db)), 1)
        self.assert_catalog_only()

    def test_multi_company_split_keeps_header_detail_trailer_output(self):
        upload_id = self.service.create_upload(self.db, "columns.txt", b"Company\nEmployee\nCount").id
        job_id = self.service.create_job(self.db, self.payload(source_key="mapped_employee_payroll_report", uploaded_query_id=upload_id,
                    client_selections={"1": [], "2": []}, export_split_by="client_id",
                    column_mappings=[{"column_name": "Company", "db_column_name": ["company_name"], "record_type": "H"},
                                     {"column_name": "Employee", "db_column_name": ["employee_name"], "record_type": "D"},
                                     {"column_name": "Count", "db_column_name": ["employee_count"], "record_type": "T"}])).id
        run = self.service.run_job(self.db, job_id)
        self.assertEqual(run.status, "Completed")
        archive = self.service.repository.files(self.db)[0]
        self.assertTrue(archive.file_name.endswith(".zip"))
        total = 0
        with zipfile.ZipFile(archive.storage_path) as stored:
            self.assertEqual(len(stored.namelist()), 2)
            for name in stored.namelist():
                rows = list(csv.reader(io.StringIO(stored.read(name).decode("utf-8"))))
                self.assertIn(rows[0][0], {"Company A", "Company B"})
                self.assertEqual(int(rows[-1][0]), len(rows) - 2)
                total += len(rows) - 2
        self.assertEqual(archive.row_count, total)
        self.assert_catalog_only()

    def test_split_report_email_is_limited_to_each_company(self):
        settings = Settings(_env_file=None, smtp_enabled=True, generated_reports_dir=f"{self.folder.name}/reports")
        upload_id = self.service.create_upload(self.db, "columns.txt", b"Company\nEmployee").id
        job_id = self.service.create_job(self.db, self.payload(source_key="mapped_employee_payroll_report", uploaded_query_id=upload_id,
                    client_selections={"1": ["a@example.com"], "2": ["b@example.com"]}, export_split_by="client_id",
                    column_mappings=[{"column_name": "Company", "db_column_name": ["company_name"]},
                                     {"column_name": "Employee", "db_column_name": ["employee_name"]}])).id
        with patch("app.services.workflow_service.get_settings", return_value=settings), patch("app.services.workflow_service.send_report_content") as send_content, patch("app.services.workflow_service.send_report") as send_archive:
            send_content.return_value = True
            run = self.service.run_job(self.db, job_id)
        self.assertEqual(run.status, "Completed")
        self.assertEqual(send_archive.call_count, 0)
        deliveries = {call.args[1][0]: call.args[2] for call in send_content.call_args_list}
        self.assertEqual(set(deliveries), {"a@example.com", "b@example.com"})
        self.assertIn("client_1_", deliveries["a@example.com"])
        self.assertIn("client_2_", deliveries["b@example.com"])
        self.assert_catalog_only()

    def test_file_name_with_multiple_companies_also_isolates_email_files(self):
        settings = Settings(_env_file=None, smtp_enabled=True, generated_reports_dir=f"{self.folder.name}/reports")
        upload_id = self.service.create_upload(self.db, "columns.txt", b"Company\nEmployee").id
        job_id = self.service.create_job(self.db, self.payload(source_key="mapped_employee_payroll_report", uploaded_query_id=upload_id,
                    client_selections={"1": ["a@example.com"], "2": ["b@example.com"]}, export_split_by="file_name",
                    column_mappings=[{"column_name": "Company", "db_column_name": ["company_name"]},
                                     {"column_name": "Employee", "db_column_name": ["employee_name"]}])).id
        with patch("app.services.workflow_service.get_settings", return_value=settings), patch("app.services.workflow_service.send_report_content") as send_content:
            run = self.service.run_job(self.db, job_id)
        self.assertEqual(run.status, "Completed")
        deliveries = {call.args[1][0]: call.args[2] for call in send_content.call_args_list}
        self.assertEqual(set(deliveries), {"a@example.com", "b@example.com"})
        self.assertIn("client_1_", deliveries["a@example.com"])
        self.assertIn("client_2_", deliveries["b@example.com"])
        self.assertTrue(self.service.repository.files(self.db)[0].file_name.endswith(".zip"))
        self.assert_catalog_only()


    def test_shared_lookups_keep_optional_filters_separate(self):
        self.assertEqual(len(records(self.db, Company, "8")), 3)
        self.assertEqual(get(self.db, Company, 1).id, 1)
        self.assertIsNone(get(self.db, Company, None))
        selected = records(self.db, Company, "8", {"company_ids": [1, 3], "filter_company_ids": True})
        self.assertEqual({company.id for company in selected}, {1, 3})
        self.assertEqual(records(self.db, Company, "8", {"company_ids": [], "filter_company_ids": True}), [])
        repository = self.service.repository
        self.assertEqual(len(repository.company_emails(self.db, 1)), 6)
        self.assertEqual(len(repository.client_emails(self.db, 1)), 2)
        self.assertEqual(repository.company_emails(self.db, -1), [])
        self.assertEqual(repository.client_emails(self.db, -1), [])
        self.assertIsNone(repository.file(self.db, None))
        self.assert_catalog_only()

    def test_scheduler_update_does_not_overwrite_a_concurrent_edit(self):
        payload = self.payload()
        job = self.service.create_job(self.db, payload)
        job_id = job.id
        with self.Session() as background:
            stale = get(background, ReportJob, job_id)
            self.service.update_job(self.db, job_id, payload.model_copy(update={"title": "Preserved edit"}))
            stale.next_run_at = datetime(2032, 1, 1)
            update(background, stale, "17", ("next_run_at",))
            background.commit()
        refresh(self.db, job)
        self.assertEqual(job.title, "Preserved edit")
        self.assertEqual(job.next_run_at, datetime(2032, 1, 1))
        self.assert_catalog_only()

    def test_single_insert_definition_supports_both_return_id_strategies(self):
        for query_id in ("13", "14", "19", "22"):
            raw = query_store.get(query_id)
            self.assertIn("-- @mssql", raw)
            server = query_store.get(query_id, dialect="mssql")
            self.assertIn("OUTPUT INSERTED.id", server)
            self.assertNotIn("-- @mssql", server)
            for dialect in ("mysql", "sqlite"):
                portable = query_store.get(query_id, dialect=dialect)
                self.assertNotIn("OUTPUT INSERTED.id", portable)
                self.assertNotIn("-- @mssql", portable)


    def test_only_company_sp_and_uploaded_sql_mapping_are_offered(self):
        reports = WorkflowController(self.service).procedures()
        self.assertEqual({report["key"] for report in reports}, {"company_payroll_report", "mapped_employee_payroll_report"})
        mapping = next(report for report in reports if report["key"] == "mapped_employee_payroll_report")
        self.assertTrue(mapping["supports_mapping"])
        self.assertEqual(mapping["name"], "Uploaded Column Mapping")
        for retired in ("employee_payroll_report", "monthly_payroll_summary", "department_payroll_report", "employee_salary_breakdown"):
            with self.subTest(retired=retired), self.assertRaisesRegex(ValueError, "approved stored procedure"):
                self.service.create_job(self.db, self.payload(source_key=retired))
        self.assert_catalog_only()


@unittest.skipUnless(os.getenv("RUN_SQLSERVER_TESTS") == "1" and get_settings().db_dialect.lower() in {"mssql", "sqlserver"}, "enable live SQL Server tests explicitly")
class JobsSqlServerQueryTests(unittest.TestCase):
    def setUp(self):
        from app.database.session import SessionLocal, engine
        self.db = SessionLocal()
        self.addCleanup(self.db.close)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        settings = get_settings().model_copy(update={"generated_reports_dir": self.folder.name, "uploads_dir": self.folder.name})
        patcher = patch("app.services.workflow_service.get_settings", return_value=settings)
        patcher.start(); self.addCleanup(patcher.stop)
        self.service = WorkflowService()
        self.company_id = self.service.repository.companies(self.db)[0].id
        self.job_id = None
        self.upload_id = None
        self.statements = []
        def capture(connection, cursor, sql, params, context, many):
            self.statements.append(context.compiled.statement if context.compiled else None)
        event.listen(engine, "before_cursor_execute", capture)
        self.addCleanup(self.cleanup_rows)
        self.addCleanup(event.remove, engine, "before_cursor_execute", capture)

    def cleanup_rows(self):
        self.db.rollback()
        if self.job_id is not None:
            for record in self.db.query(GeneratedFile).filter(GeneratedFile.job_id == self.job_id).all(): self.db.delete(record)
            for record in self.db.query(JobRun).filter(JobRun.job_id == self.job_id).all(): self.db.delete(record)
            record = self.db.get(ReportJob, self.job_id)
            if record is not None: self.db.delete(record)
        if self.upload_id is not None:
            record = self.db.get(UploadedQuery, self.upload_id)
            if record is not None: self.db.delete(record)
        self.db.commit()

    def payload(self, **overrides):
        values = dict(title="itest-numbered-jobs", display_name="SQL catalog", company_id=self.company_id,
                      source_type="procedure", source_key="company_payroll_report",
                      schedule_at=datetime.now(KOLKATA) + timedelta(days=2), schedule_type="daily")
        values.update(overrides)
        return JobCreate(**values)

    def assert_catalog_only(self):
        self.assertTrue(self.statements)
        self.assertTrue(all(isinstance(statement, (TextClause, TextualSelect)) for statement in self.statements),
                        [type(statement).__name__ for statement in self.statements])

    def test_create_update_toggle_execute_and_generated_identity(self):
        payload = self.payload(schedule_type="hourly_2")
        job = self.service.create_job(self.db, payload)
        self.job_id = job.id
        self.assertIsInstance(job.id, int)
        self.assertIsInstance(job.updated_at, datetime)
        self.assertEqual(job.schedule_type, "hourly_2")
        self.assertEqual(SchedulerService.build_trigger(job).interval, timedelta(hours=2))
        job = self.service.update_job(self.db, self.job_id, payload.model_copy(update={"title": "itest-numbered-jobs-edited"}))
        self.assertEqual(job.title, "itest-numbered-jobs-edited")
        self.assertFalse(self.service.set_enabled(self.db, self.job_id, False).enabled)
        self.service.set_enabled(self.db, self.job_id, True)
        run = self.service.run_job(self.db, self.job_id)
        self.assertEqual(run.status, "Completed")
        files = [record for record in self.service.repository.files(self.db) if record.job_id == self.job_id]
        self.assertEqual(len(files), 1)
        self.assertIsInstance(files[0].id, int)
        self.assertTrue(Path(files[0].storage_path).is_file())
        self.assert_catalog_only()

    def test_uploaded_mapping_with_bound_company_list(self):
        uploaded = self.service.create_upload(self.db, "columns.txt", b"Employee\nSalary")
        self.upload_id = uploaded.id
        self.assertIsInstance(uploaded.id, int)
        job = self.service.create_job(self.db, self.payload(source_key="mapped_employee_payroll_report", uploaded_query_id=self.upload_id,
                    client_selections={str(self.company_id): []},
                    column_mappings=[{"column_name": "Employee", "db_column_name": ["employee_name"]},
                                     {"column_name": "Salary", "db_column_name": ["net_salary"]}]))
        self.job_id = job.id
        run = self.service.run_job(self.db, self.job_id)
        self.assertEqual(run.status, "Completed")
        self.assertIn("Employee", run.csv_content)
        self.assert_catalog_only()
