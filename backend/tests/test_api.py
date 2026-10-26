"""HTTP-level tests with an in-memory SQLite session and a fake LDAP directory.

They validate routing, Pydantic validation, error mapping and JWT handling. They do not
prove SQL Server or Active Directory connectivity; see test_sqlserver_integration.py.
"""
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import Settings, get_settings
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import User
from app.routes import auth as auth_routes
from app.utils.auth_exceptions import AuthenticationUnavailableError, InvalidCredentialsError

PASSWORD = "correct-horse-battery-staple"


def make_settings(**values):
    return Settings(_env_file=None, **values)


class FakeDirectory:
    """Accepts exactly one username/password pair, like a directory with one account."""

    def __init__(self):
        self.available = True
        self.groups = ["Report Users", "Domain Admins"]

    def canonical_username(self, username: str) -> str:
        return username.strip().split("\\")[-1].split("@")[0].lower()

    def authenticate(self, username: str, password: str):
        if not self.available:
            raise AuthenticationUnavailableError("LDAP service is unavailable.")
        if self.canonical_username(username) != "alice" or password != PASSWORD:
            raise InvalidCredentialsError("Invalid username or password.")
        return {
            "username": "alice", "email": "alice@example.test", "full_name": "Alice Example", "department": "Finance",
            "title": "Analyst", "user_principal_name": "alice@agile.local", "groups": list(self.groups),
        }


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.directory = FakeDirectory()
        service = auth_routes.controller.service
        self.ldap_patch = patch.object(service, "ldap", self.directory)
        self.ldap_patch.start()
        service.limiter.attempts.clear()
        self.client = TestClient(app)

    def tearDown(self):
        self.ldap_patch.stop()
        auth_routes.controller.service.limiter.attempts.clear()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def login(self, username="alice", password=PASSWORD):
        return self.client.post("/api/auth/login", json={"username": username, "password": password})


class HealthAndReportTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        response = self.login()
        self.report_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_health_endpoints(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        response = self.client.get("/health/database")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "reachable"})

    def test_create_and_list_reports(self):
        response = self.client.post("/api/reports", json={"title": "Quarterly", "description": "Q3"}, headers=self.report_headers)
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(set(body), {"id", "title", "description", "created_at"})
        self.assertEqual(body["title"], "Quarterly")
        listed = self.client.get("/api/reports", headers=self.report_headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([item["id"] for item in listed.json()], [body["id"]])

    def test_report_validation_errors(self):
        cases = {
            "missing title": {"description": "no title"},
            "empty title": {"title": ""},
            "title too long": {"title": "x" * 256},
            "wrong type": {"title": ["not", "a", "string"]},
            "empty object": {},
        }
        for name, payload in cases.items():
            with self.subTest(name):
                self.assertEqual(self.client.post("/api/reports", json=payload, headers=self.report_headers).status_code, 422)
        self.assertEqual(self.client.post("/api/reports", headers=self.report_headers).status_code, 422)
        self.assertEqual(
            self.client.post("/api/reports", content="{not json", headers={**self.report_headers, "Content-Type": "application/json"}).status_code,
            422,
        )
        self.assertEqual(self.client.get("/api/reports", headers=self.report_headers).json(), [])

    def test_database_failure_returns_generic_error(self):
        broken = create_engine("sqlite:////nonexistent-dir/forbidden.db")

        def broken_db():
            db = sessionmaker(bind=broken)()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = broken_db
        health = self.client.get("/health/database")
        self.assertEqual(health.status_code, 503)
        self.assertEqual(health.json(), {"detail": "Database is unavailable."})
        listing = self.client.get("/api/reports", headers=self.report_headers)
        self.assertEqual(listing.status_code, 500)
        self.assertEqual(listing.json(), {"detail": "Could not fetch reports."})
        created = self.client.post("/api/reports", json={"title": "x"}, headers=self.report_headers)
        self.assertEqual(created.json(), {"detail": "Could not create the report."})
        self.assertNotIn("nonexistent", created.text)

    def test_cors_preflight_allows_only_configured_origins(self):
        allowed = self.client.options(
            "/api/reports", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"}
        )
        self.assertEqual(allowed.headers.get("access-control-allow-origin"), "http://localhost:5173")
        denied = self.client.options(
            "/api/reports", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"}
        )
        self.assertNotIn("access-control-allow-origin", denied.headers)


class StartupTests(unittest.TestCase):
    def test_startup_refuses_default_or_short_jwt_secret(self):
        from app import main
        from app.config.settings import DEFAULT_JWT_SECRET, PLACEHOLDER_JWT_SECRET, Settings

        for secret in (DEFAULT_JWT_SECRET, PLACEHOLDER_JWT_SECRET, "short-secret"):
            with self.subTest(secret=secret), patch.object(main, "settings", Settings(jwt_secret_key=secret)):
                with self.assertRaises(RuntimeError), TestClient(main.app):
                    pass
        with patch.object(main, "settings", Settings(jwt_secret_key="x" * 40)), TestClient(main.app) as client:
            self.assertEqual(client.get("/health").status_code, 200)


class AuthApiTests(ApiTestCase):
    def test_login_creates_user_and_token_grants_access(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["token_type"], "bearer")
        self.assertEqual(body["user"]["username"], "alice")
        self.assertNotIn(PASSWORD, response.text)
        claims = jwt.decode(body["access_token"], options={"verify_signature": False})
        self.assertEqual(claims["sub"], "alice")
        self.assertIn("exp", claims)

        me = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "alice@example.test")

        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 1)
        columns = {column["name"] for column in inspect(self.engine).get_columns("users")}
        self.assertFalse(any("password" in column for column in columns))

    def test_login_failures(self):
        cases = {
            "wrong password": ({"username": "alice", "password": "wrong"}, 401),
            "unknown user": ({"username": "mallory", "password": PASSWORD}, 401),
            "empty username": ({"username": "", "password": PASSWORD}, 422),
            "empty password": ({"username": "alice", "password": ""}, 422),
            "missing password": ({"username": "alice"}, 422),
            "wrong type": ({"username": 123, "password": PASSWORD}, 422),
        }
        for name, (payload, expected) in cases.items():
            with self.subTest(name):
                response = self.client.post("/api/auth/login", json=payload)
                self.assertEqual(response.status_code, expected)
                if expected == 401:
                    # Same message for unknown users and wrong passwords: no account enumeration.
                    self.assertEqual(response.json(), {"detail": "Invalid username or password."})
                    self.assertNotIn("WWW-Authenticate", response.headers)

    def test_validation_errors_do_not_echo_submitted_values(self):
        secret = "do-not-echo-this-password"
        for payload in ({"password": secret}, {"username": "alice", "password": secret * 30}):
            with self.subTest(sorted(payload)):
                response = self.client.post("/api/auth/login", json=payload)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn(secret, response.text)
                self.assertTrue(all({"type", "loc", "msg"} <= set(error) for error in response.json()["detail"]))

    def test_all_username_formats_log_in_as_the_same_user(self):
        ids = {self.login(name).json()["user"]["id"] for name in ("alice", "AGILE\\alice", "alice@agile.local")}
        self.assertEqual(len(ids), 1)

    def test_me_returns_directory_profile_and_permissions_but_not_groups(self):
        mapping = make_settings(ldap_group_permissions="Report Users=reports:read")
        with patch.object(auth_routes.controller.service.authorizer, "settings", mapping):
            token = self.login().json()["access_token"]
        me = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
        self.assertEqual((me["department"], me["title"], me["permissions"]), ("Finance", "Analyst", ["reports:read"]))
        self.assertNotIn("groups", me)
        self.assertNotIn("Domain Admins", str(me))

    def test_user_outside_allowed_groups_gets_403_and_no_token(self):
        restricted = make_settings(ldap_allowed_groups="Scheduler Users")
        with patch.object(auth_routes.controller.service.authorizer, "settings", restricted):
            response = self.login()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Not authorized to use this application."})
        self.assertNotIn("access_token", response.text)
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 0)

    def test_ldap_unavailable_returns_503(self):
        self.directory.available = False
        response = self.login()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Authentication service is unavailable."})

    def test_rate_limit_applies_per_account_regardless_of_case(self):
        limit = get_settings().login_max_attempts
        for attempt in range(limit):
            name = "alice" if attempt % 2 else "ALICE "
            self.assertEqual(self.login(name, "wrong").status_code, 401)
        self.assertEqual(self.login().status_code, 429)

    def test_successful_login_resets_rate_limit(self):
        limit = get_settings().login_max_attempts
        for _ in range(limit - 1):
            self.login(password="wrong")
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.login(password="wrong").status_code, 401)

    def test_me_rejects_missing_invalid_tampered_and_expired_tokens(self):
        token = self.login().json()["access_token"]
        settings = get_settings()
        header, payload, signature = token.split(".")
        forged_payload = jwt.utils.base64url_encode(b'{"sub":"admin","exp":9999999999}').decode()
        expired = jwt.encode(
            {"sub": "alice", "exp": datetime.now(UTC) - timedelta(seconds=1)},
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        wrong_key = jwt.encode(
            {"sub": "alice", "exp": datetime.now(UTC) + timedelta(minutes=5)}, "another-secret-of-sufficient-length!!", algorithm="HS256"
        )
        unsigned = jwt.encode({"sub": "alice"}, None, algorithm="none")
        cases = {
            "missing": {},
            "garbage": {"Authorization": "Bearer not-a-token"},
            "tampered payload": {"Authorization": f"Bearer {header}.{forged_payload}.{signature}"},
            "tampered signature": {"Authorization": f"Bearer {header}.{payload}.{signature[:-4]}AAAA"},
            "expired": {"Authorization": f"Bearer {expired}"},
            "wrong key": {"Authorization": f"Bearer {wrong_key}"},
            "alg none": {"Authorization": f"Bearer {unsigned}"},
            "wrong scheme": {"Authorization": f"Basic {token}"},
        }
        for name, headers in cases.items():
            with self.subTest(name):
                self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 401)

    def test_token_for_deleted_or_inactive_user_is_rejected(self):
        token = self.login().json()["access_token"]
        with self.Session() as db:
            db.query(User).update({"is_active": False})
            db.commit()
        self.assertEqual(self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
