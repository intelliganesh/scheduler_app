"""Live Microsoft SQL Server integration tests.

Skipped unless RUN_SQLSERVER_TESTS=1 and the configured dialect is mssql. They use the
real engine from backend/.env, create rows tagged with a unique prefix, and delete only
those rows. Run after the configured SQL Server is reachable and `alembic upgrade head`:

    RUN_SQLSERVER_TESTS=1 .venv/bin/python -m unittest tests.test_sqlserver_integration -v
"""
import os
import unittest
import uuid
from unittest.mock import patch

from app.config.settings import get_settings

LIVE = os.getenv("RUN_SQLSERVER_TESTS") == "1" and get_settings().db_dialect.lower() in {"mssql", "sqlserver"}


@unittest.skipUnless(LIVE, "set RUN_SQLSERVER_TESTS=1 with DB_DIALECT=mssql to run live SQL Server tests")
class SqlServerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from sqlalchemy import text

        from app.database.session import SessionLocal, engine
        from app.main import app

        cls.text = staticmethod(text)
        cls.engine = engine
        cls.SessionLocal = SessionLocal
        cls.client = TestClient(app)
        from app.utils.security import create_access_token
        cls.report_headers = {"Authorization": f"Bearer {create_access_token('sqlserver-integration', ['dashboard', 'create_job'], [])}"}
        cls.tag = f"itest-{uuid.uuid4().hex[:10]}"

    @classmethod
    def tearDownClass(cls):
        with cls.SessionLocal() as db:
            db.execute(cls.text("DELETE FROM reports WHERE title LIKE :tag"), {"tag": f"{cls.tag}%"})
            db.execute(cls.text("DELETE FROM users WHERE username LIKE :tag"), {"tag": f"{cls.tag}%"})
            db.commit()

    def name(self, suffix: str) -> str:
        return f"{self.tag}-{suffix}"

    def scalar(self, sql: str, **params):
        with self.SessionLocal() as db:
            return db.execute(self.text(sql), params).scalar()

    def test_server_is_developer_edition_and_schema_is_current(self):
        self.assertIn("Developer", self.scalar("SELECT CAST(SERVERPROPERTY('Edition') AS nvarchar(128))"))
        self.assertEqual(self.engine.dialect.name, "mssql")
        self.assertEqual(self.engine.driver, "pyodbc")
        self.assertEqual(self.scalar("SELECT DB_NAME()"), get_settings().db_name)
        self.assertEqual(self.scalar("SELECT encrypt_option FROM sys.dm_exec_connections WHERE session_id = @@SPID"), "TRUE")
        tables = self.scalar(
            "SELECT STRING_AGG(name, ',') WITHIN GROUP (ORDER BY name) FROM sys.tables "
            "WHERE name IN ('alembic_version', 'reports', 'users')"
        )
        self.assertEqual(tables, "alembic_version,reports,users")
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        self.assertEqual(self.scalar("SELECT version_num FROM alembic_version"), head)

    def test_report_repository_crud(self):
        from app.models import Report
        from app.repositories.report_repository import ReportRepository
        from app.schemas.report import ReportCreate

        repository = ReportRepository()
        with self.SessionLocal() as db:
            created = repository.create(db, ReportCreate(title=self.name("crud"), description="initial"))
            self.assertIsNotNone(created.id)
            self.assertIsNotNone(created.created_at)
            self.assertIn(created.id, [report.id for report in repository.list(db)])
            created.description = "updated"
            db.commit()
            report_id = created.id
        with self.SessionLocal() as db:
            self.assertEqual(db.get(Report, report_id).description, "updated")
            db.delete(db.get(Report, report_id))
            db.commit()
        with self.SessionLocal() as db:
            self.assertIsNone(db.get(Report, report_id))

    def test_unicode_text_round_trips(self):
        from app.models import Report

        title = self.name("ವರದಿ रिपोर्ट ✓")
        with self.SessionLocal() as db:
            report = Report(title=title, description="ünïcödé — 報告")
            db.add(report)
            db.commit()
            report_id = report.id
        with self.SessionLocal() as db:
            stored = db.get(Report, report_id)
            self.assertEqual((stored.title, stored.description), (title, "ünïcödé — 報告"))

    def test_rollback_discards_uncommitted_rows(self):
        from app.models import Report

        title = self.name("rollback")
        with self.SessionLocal() as db:
            db.add(Report(title=title))
            db.flush()
            self.assertEqual(db.query(Report).filter_by(title=title).count(), 1)
            db.rollback()
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM reports WHERE title = :title", title=title), 0)

    def test_user_constraints(self):
        from sqlalchemy.exc import IntegrityError

        from app.models import User

        with self.SessionLocal() as db:
            db.add_all([User(username=self.name("null-a")), User(username=self.name("null-b"))])
            db.commit()  # several users without an AD mail attribute are allowed
            db.add(User(username=self.name("mail-a"), email=f"{self.tag}@example.test"))
            db.commit()
        for duplicate in (User(username=self.name("mail-b"), email=f"{self.tag}@example.test"), User(username=self.name("null-a"))):
            with self.subTest(duplicate.username), self.SessionLocal() as db:
                db.add(duplicate)
                with self.assertRaises(IntegrityError):
                    db.commit()
                db.rollback()

    def test_sessions_are_returned_to_the_pool(self):
        from app.database.session import get_db

        before = self.engine.pool.checkedout()
        dependency = get_db()
        db = next(dependency)
        db.execute(self.text("SELECT 1"))
        self.assertEqual(self.engine.pool.checkedout(), before + 1)
        dependency.close()
        self.assertEqual(self.engine.pool.checkedout(), before)

    def test_api_report_flow_persists_to_sql_server(self):
        self.assertEqual(self.client.get("/health/database").json(), {"status": "ok", "database": "reachable"})
        title = self.name("api")
        created = self.client.post("/api/reports", json={"title": title, "description": "via API"}, headers=self.report_headers)
        self.assertEqual(created.status_code, 201)
        report_id = created.json()["id"]
        self.assertIn(report_id, [item["id"] for item in self.client.get("/api/reports", headers=self.report_headers).json()])
        self.assertEqual(self.scalar("SELECT description FROM reports WHERE id = :id", id=report_id), "via API")
        self.assertEqual(self.client.post("/api/reports", json={"title": ""}, headers=self.report_headers).status_code, 422)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM reports WHERE title = ''"), 0)

    def test_mocked_ldap_login_creates_updates_and_authorizes_user(self):
        """LDAP is mocked; SQL Server, JWT and the HTTP layer are real."""
        from app.routes import auth as auth_routes

        username = self.name("ldap")
        password = f"pw-{uuid.uuid4().hex}"
        profiles = iter([
            {"username": username, "email": None, "full_name": "First Name"},
            {"username": username, "email": f"{username}@example.test", "full_name": "Updated Name"},
        ])
        service = auth_routes.controller.service
        with patch.object(service.ldap, "authenticate", side_effect=lambda u, p: next(profiles)):
            first = self.client.post("/api/auth/login", json={"username": username, "password": password})
            second = self.client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(first.json()["user"]["id"], second.json()["user"]["id"])
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users WHERE username = :u", u=username), 1)
        self.assertEqual(self.scalar("SELECT full_name FROM users WHERE username = :u", u=username), "Updated Name")
        password_columns = self.scalar("SELECT COUNT(*) FROM sys.columns WHERE object_id = OBJECT_ID('users') AND name LIKE '%pass%'")
        self.assertEqual(password_columns, 0)

        token = second.json()["access_token"]
        me = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], f"{username}@example.test")
        self.assertEqual(self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}x"}).status_code, 401)

    def test_active_directory_profile_sync(self):
        """Directory responses are mocked; the AuthService, repository and SQL Server are real."""
        from app.config.settings import Settings
        from app.models import User
        from app.repositories.user_repository import UserRepository
        from app.services.auth_service import AuthService, GroupAuthorizer, LoginRateLimiter
        from app.utils.auth_exceptions import AuthorizationDeniedError

        username = self.name("ad")
        settings = Settings(ldap_group_permissions="Report Users=reports:read,reports:write", ldap_allowed_groups="")
        profiles = [
            {"username": username, "email": None, "full_name": "ಜೇನ್ ಡೋ", "given_name": "ಜೇನ್", "surname": "ಡೋ",
             "department": "ಹಣಕಾಸು", "title": None, "company": "Agile", "user_principal_name": None, "groups": ["Report Users"]},
            {"username": username, "email": f"{username}@agile.local", "full_name": "Jane Doe", "given_name": "Jane",
             "surname": "Doe", "department": "Finance", "title": "Analyst", "company": "Agile",
             "user_principal_name": f"{username}@agile.local", "groups": ["Domain Users"]},
        ]

        class Directory:
            def authenticate(self, _username, _password):
                return dict(profiles.pop(0))

        service = AuthService(ldap=Directory(), repository=UserRepository(), limiter=LoginRateLimiter(settings),
                              authorizer=GroupAuthorizer(settings))
        with self.SessionLocal() as db:
            first = service.login(db, username, "not-stored")
            self.assertEqual((first.full_name, first.department, first.email), ("ಜೇನ್ ಡೋ", "ಹಣಕಾಸು", None))
            self.assertEqual(first.permissions, "reports:read,reports:write")
            second = service.login(db, username, "not-stored")
            self.assertEqual(second.id, first.id)
        with self.SessionLocal() as db:
            stored = db.query(User).filter_by(username=username).one()
            self.assertEqual((stored.full_name, stored.title, stored.email), ("Jane Doe", "Analyst", f"{username}@agile.local"))
            self.assertIsNone(stored.permissions)  # mapping recomputed on every login: no longer in Report Users
        stored_text = self.scalar(
            "SELECT CONCAT(username, email, full_name, user_principal_name, given_name, surname, department, title, company, permissions) "
            "FROM users WHERE username = :u", u=username,
        )
        self.assertNotIn("not-stored", stored_text)

        denied = AuthService(
            ldap=type("D", (), {"authenticate": lambda self, u, p: {"username": username, "full_name": "Changed", "groups": []}})(),
            limiter=LoginRateLimiter(settings), authorizer=GroupAuthorizer(Settings(ldap_allowed_groups="Report Users")),
        )
        with self.SessionLocal() as db, self.assertRaises(AuthorizationDeniedError):
            denied.login(db, username, "x")
        self.assertEqual(self.scalar("SELECT full_name FROM users WHERE username = :u", u=username), "Jane Doe")

    def test_unreachable_server_fails_safely(self):
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import OperationalError
        from sqlalchemy.orm import sessionmaker

        from app.database.session import get_db
        from app.main import app

        url = self.engine.url.set(port=1)
        broken = create_engine(url, connect_args={"timeout": 3})
        with self.assertRaises(OperationalError):
            with broken.connect() as connection:
                connection.execute(text("SELECT 1"))

        def broken_db():
            db = sessionmaker(bind=broken)()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = broken_db
        try:
            health = self.client.get("/health/database")
            reports = self.client.get("/api/reports", headers=self.report_headers)
        finally:
            app.dependency_overrides.clear()
            broken.dispose()
        self.assertEqual((health.status_code, health.json()), (503, {"detail": "Database is unavailable."}))
        self.assertEqual((reports.status_code, reports.json()), (500, {"detail": "Could not fetch reports."}))
        password = get_settings().db_password
        for body in (health.text, reports.text):
            self.assertNotIn(password, body)
            self.assertNotIn("ODBC", body)


if __name__ == "__main__":
    unittest.main()
