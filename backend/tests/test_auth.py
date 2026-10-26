import os
import re
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import jwt
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings
from app.database.base import Base
from app.models import User
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService, GroupAuthorizer, LoginRateLimiter
from app.services.ldap_service import LdapService, md4_available, ntlm_session_encryption_supported, sid_to_string
from app.utils.auth_exceptions import (
    AuthenticationUnavailableError,
    AuthorizationDeniedError,
    InvalidCredentialsError,
    LoginRateLimitedError,
)
from app.utils.security import create_access_token, get_token_subject


def make_settings(**values):
    """Settings isolated from backend/.env, which may hold real directory configuration."""
    return Settings(_env_file=None, **values)


class FakeLdap:
    def authenticate(self, username: str, password: str):
        self.last = (username, password)
        return {"username": username, "email": f"{username}@example.com", "full_name": "Test User"}


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_ldap_requires_explicit_configuration(self):
        with self.assertRaises(AuthenticationUnavailableError):
            LdapService(make_settings(ldap_enabled=False)).authenticate("person", "secret")

    def test_login_upserts_user_without_storing_password(self):
        settings = make_settings(login_max_attempts=5, login_window_seconds=60)
        service = AuthService(ldap=FakeLdap(), repository=UserRepository(), limiter=LoginRateLimiter(settings))
        user = service.login(self.db, "person", "secret")
        self.assertEqual(user.username, "person")
        self.assertEqual(user.email, "person@example.com")
        self.assertEqual(self.db.query(User).count(), 1)

    def test_subsequent_login_updates_existing_profile(self):
        ldap = FakeLdap()
        service = AuthService(ldap=ldap, repository=UserRepository(), limiter=LoginRateLimiter(make_settings()))
        service.login(self.db, "person", "first")
        ldap.authenticate = lambda username, password: {"username": username, "email": "updated@example.com", "full_name": "Updated User"}
        user = service.login(self.db, "person", "second")
        self.assertEqual(user.email, "updated@example.com")
        self.assertEqual(user.full_name, "Updated User")
        self.assertEqual(self.db.query(User).count(), 1)

    def test_login_rate_limit(self):
        limiter = LoginRateLimiter(make_settings(login_max_attempts=1, login_window_seconds=60))
        limiter.check("person")
        with self.assertRaises(LoginRateLimitedError):
            limiter.check("person")


AGILE = {
    "ldap_enabled": True,
    "ldap_host": "dc01.agile.local",
    "ldap_port": 389,
    "ldap_base_dn": "DC=agile,DC=local",
    "ldap_domain": "agile.local",
    "ldap_netbios_domain": "AGILE",
    "ldap_auth_method": "NTLM",
    "ldap_use_ssl": False,
    "ldap_start_tls": True,
    "ldap_search_timeout_seconds": 7,
}
DOMAIN_SID = "S-1-5-21-1111-2222-3333"
JDOE_DN = "CN=Jane Doe,OU=Staff,DC=agile,DC=local"
GROUP_DN = "CN={},OU=Groups,DC=agile,DC=local"


class FakeAttribute:
    def __init__(self, values):
        self.values = values
        self.value = values[0] if len(values) == 1 else values


class FakeEntry:
    """Behaves like an ldap3 Entry for `in`, `[...]`, `.values`, `.value` and `entry_dn`."""

    def __init__(self, dn, **attributes):
        self.entry_dn = dn
        self._attributes = {k: v if isinstance(v, list) else [v] for k, v in attributes.items() if v is not None}

    def __contains__(self, name):
        return name in self._attributes

    def __getitem__(self, name):
        return FakeAttribute(self._attributes[name])


class FakeActiveDirectory:
    """A tiny in-memory AD: accounts, NTLM/simple credentials, nested groups and a primary group."""

    def __init__(self):
        self.users = {
            "jdoe": FakeEntry(
                JDOE_DN, sAMAccountName="jdoe", userPrincipalName="jdoe@agile.local", displayName="ಜೇನ್ ಡೋ (Jane Doe)",
                givenName="Jane", sn="Doe", mail="jane.doe@agile.local", department="Finance", title="Analyst",
                company="Agile", memberOf=[GROUP_DN.format("Report Users"), GROUP_DN.format("docker-users")],
                primaryGroupID="513", objectSid=f"{DOMAIN_SID}-1105",
            ),
            "bare": FakeEntry("CN=bare,OU=Staff,DC=agile,DC=local", sAMAccountName="bare", primaryGroupID="513"),
            "admin": FakeEntry(
                "CN=Administrator,CN=Users,DC=agile,DC=local", sAMAccountName="Administrator",
                memberOf=[GROUP_DN.format("Domain Admins")], primaryGroupID="513", objectSid=f"{DOMAIN_SID}-500",
            ),
        }
        self.passwords = {
            "agile\\jdoe": "jdoe-pass", "jdoe@agile.local": "jdoe-pass", JDOE_DN.lower(): "jdoe-pass",
            "agile\\bare": "bare-pass", "agile\\svc-reader": "svc-pass", "cn=svc,dc=agile,dc=local": "svc-pass",
        }
        # group CN -> (SID, direct members)
        self.groups = {
            "Report Users": (f"{DOMAIN_SID}-2001", [JDOE_DN]),
            "Scheduler Users": (f"{DOMAIN_SID}-2002", [GROUP_DN.format("Report Users")]),  # nested
            "docker-users": (f"{DOMAIN_SID}-2003", [JDOE_DN]),
            "Domain Admins": (f"{DOMAIN_SID}-512", ["CN=Administrator,CN=Users,DC=agile,DC=local"]),
            "Domain Users": (f"{DOMAIN_SID}-513", []),  # primary group: membership is implicit
        }
        self.bind_failure_code = 49
        self.readable = True
        self.raise_on_bind = None
        self.connections = []

    def connect(self, server, **options):
        connection = FakeConnection(self, options)
        self.connections.append(connection)
        return connection

    def transitive_groups(self, dn):
        found, frontier = set(), {dn}
        while frontier:
            current = frontier.pop()
            for name, (_, members) in self.groups.items():
                if current in members and name not in found:
                    found.add(name)
                    frontier.add(GROUP_DN.format(name))
        return found


def unescape(value):
    return re.sub(r"\\([0-9a-fA-F]{2})", lambda match: chr(int(match.group(1), 16)), value)


class FakeConnection:
    def __init__(self, directory, options):
        self.directory, self.options = directory, options
        self.calls, self.searches, self.entries, self.result = [], [], [], None

    def open(self):
        self.calls.append("open")

    def start_tls(self):
        self.calls.append("start_tls")

    def bind(self):
        self.calls.append("bind")
        if self.directory.raise_on_bind:
            raise self.directory.raise_on_bind
        ok = self.directory.passwords.get(self.options["user"].lower()) == self.options["password"]
        ok = ok and self.directory.bind_failure_code == 49  # other codes model a DC rejecting every bind
        self.result = {"result": 0 if ok else self.directory.bind_failure_code}
        return ok

    def search(self, base, search_filter, **options):
        self.searches.append((base, search_filter, options))
        directory, entries = self.directory, []
        if match := re.search(r"\(sAMAccountName=([^)]*)\)", search_filter):
            account = unescape(match.group(1)).lower()
            entry = next((e for key, e in directory.users.items() if key.lower() == account or e["sAMAccountName"].value.lower() == account), None)
            entries = [entry] if entry and directory.readable else []
        elif match := re.search(r"\(member:1\.2\.840\.113556\.1\.4\.1941:=([^)]*)\)", search_filter):
            names = directory.transitive_groups(unescape(match.group(1)))
            entries = [FakeEntry(GROUP_DN.format(name), cn=name) for name in sorted(names)]
        elif match := re.search(r"\(objectClass=group\)\(cn=([^)]*)\)", search_filter):
            name = unescape(match.group(1))
            entries = [FakeEntry(GROUP_DN.format(name), cn=name)] if name in directory.groups else []
        elif match := re.search(r"\(objectSid=([^)]*)\)", search_filter):
            sid = unescape(match.group(1))
            entries = [FakeEntry(GROUP_DN.format(n), cn=n) for n, (group_sid, _) in directory.groups.items() if group_sid == sid]
        self.entries = entries
        self.result = {"result": 0}
        return bool(entries)

    def unbind(self):
        self.calls.append("unbind")


class LdapServiceTests(unittest.TestCase):
    """Mocked Active Directory: no network. Live AD tests are in scripts/ldap_live_check.py."""

    def setUp(self):
        self.directory = FakeActiveDirectory()
        patches = [
            patch("app.services.ldap_service.Connection", side_effect=self.directory.connect),
            patch("app.services.ldap_service.Server"),
            patch("app.services.ldap_service.md4_available", return_value=True),
        ]
        self.connection_class, self.server, _ = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)

    def service(self, **changes):
        return LdapService(make_settings(**{**AGILE, **changes}))

    def assert_all_unbound(self):
        for connection in self.directory.connections:
            self.assertEqual(connection.calls[-1], "unbind")

    def test_username_formats_resolve_to_the_same_account(self):
        for username in ("jdoe", "AGILE\\jdoe", "agile\\JDOE", "jdoe@agile.local", "  jdoe  "):
            with self.subTest(username=username):
                profile = self.service().authenticate(username, "jdoe-pass")
                self.assertEqual(profile["username"], "jdoe")
                self.assertEqual(self.directory.connections[-1].options["user"], "AGILE\\" + username.strip().split("\\")[-1].split("@")[0])

    def test_ntlm_bind_uses_starttls_timeouts_and_closes_connections(self):
        self.service().authenticate("AGILE\\jdoe", "jdoe-pass")
        connection = self.directory.connections[0]
        self.assertEqual(str(connection.options["authentication"]), "NTLM")
        self.assertEqual(connection.calls[:3], ["open", "start_tls", "bind"])
        self.assertEqual(connection.options["receive_timeout"], 7)
        self.assertTrue(all(options["time_limit"] == 7 for _, _, options in connection.searches))
        self.assertEqual(self.server.call_args.kwargs["connect_timeout"], 5)
        self.assertNotIn("session_security", connection.options)
        self.assert_all_unbound()

    def test_profile_and_groups_are_mapped(self):
        profile = self.service().authenticate("jdoe", "jdoe-pass")
        self.assertEqual(profile["email"], "jane.doe@agile.local")
        self.assertEqual(profile["full_name"], "ಜೇನ್ ಡೋ (Jane Doe)")
        self.assertEqual(
            {k: profile[k] for k in ("user_principal_name", "given_name", "surname", "department", "title", "company")},
            {"user_principal_name": "jdoe@agile.local", "given_name": "Jane", "surname": "Doe", "department": "Finance",
             "title": "Analyst", "company": "Agile"},
        )
        # direct (Report Users, docker-users), nested (Scheduler Users via Report Users), primary (Domain Users)
        self.assertEqual(profile["groups"], ["Domain Users", "Report Users", "Scheduler Users", "docker-users"])
        self.assertNotIn("Domain Admins", profile["groups"])

    def test_missing_attributes_are_handled(self):
        profile = self.service().authenticate("bare", "bare-pass")
        self.assertEqual(profile["username"], "bare")
        self.assertIsNone(profile["email"])
        self.assertEqual(profile["full_name"], "bare")
        self.assertIsNone(profile["department"])
        self.assertEqual(profile["groups"], [])  # no objectSid, so no primary group lookup

    def test_nested_group_lookup_can_be_disabled_and_is_size_limited(self):
        profile = self.service(ldap_nested_groups=False).authenticate("jdoe", "jdoe-pass")
        self.assertNotIn("Scheduler Users", profile["groups"])
        self.service(ldap_group_size_limit=25).authenticate("jdoe", "jdoe-pass")
        nested = [o for _, f, o in self.directory.connections[-1].searches if "1.2.840.113556.1.4.1941" in f]
        self.assertEqual(nested[0]["size_limit"], 25)

    def test_wrong_password_is_invalid_credentials(self):
        with self.assertRaises(InvalidCredentialsError):
            self.service().authenticate("jdoe", "wrong")
        self.assert_all_unbound()

    def test_non_credential_bind_failure_is_unavailable(self):
        self.directory.bind_failure_code = 8  # strongerAuthRequired, e.g. the DC requires signing
        with self.assertRaises(AuthenticationUnavailableError):
            self.service().authenticate("jdoe", "jdoe-pass")

    def test_unreadable_entry_after_successful_bind_is_unavailable(self):
        self.directory.readable = False
        with self.assertRaises(AuthenticationUnavailableError):
            self.service().authenticate("jdoe", "jdoe-pass")
        self.assert_all_unbound()

    def test_ldap_exceptions_become_generic_service_errors(self):
        from ldap3.core.exceptions import LDAPSocketOpenError

        self.directory.raise_on_bind = LDAPSocketOpenError("socket ssl wrapping error: certificate verify failed")
        with self.assertRaises(AuthenticationUnavailableError) as raised:
            self.service().authenticate("jdoe", "jdoe-pass")
        self.assertEqual(str(raised.exception), "LDAP service is unavailable.")
        self.assert_all_unbound()

    def test_foreign_domains_and_invalid_names_never_reach_the_directory(self):
        for username in ("OTHER\\jdoe", "jdoe@evil.example", "a*b", "jdoe=x", "", "   ", "x" * 65, "AGILE\\"):
            with self.subTest(username=username), self.assertRaises(InvalidCredentialsError):
                self.service().authenticate(username, "jdoe-pass")
        with self.assertRaises(InvalidCredentialsError):
            self.service().authenticate("jdoe", "")
        self.connection_class.assert_not_called()

    def test_search_filter_escapes_ldap_metacharacters(self):
        with self.assertRaises(AuthenticationUnavailableError):  # bind fails for this odd name
            self.directory.passwords["agile\\j)(cn"] = "p"
            self.directory.readable = False
            self.service().authenticate("j)(cn", "p")
        search_filter = self.directory.connections[0].searches[0][1]
        self.assertIn(r"(sAMAccountName=j\29\28cn)", search_filter)

    def test_simple_bind_uses_upn(self):
        self.service(ldap_auth_method="SIMPLE").authenticate("AGILE\\jdoe", "jdoe-pass")
        connection = self.directory.connections[0]
        self.assertEqual(connection.options["user"], "jdoe@agile.local")
        self.assertEqual(str(connection.options["authentication"]), "SIMPLE")

    def test_service_account_lookup_then_user_bind(self):
        profile = self.service(ldap_bind_dn="AGILE\\svc-reader", ldap_bind_password="svc-pass").authenticate("jdoe", "jdoe-pass")
        lookup, user = self.directory.connections
        self.assertEqual((lookup.options["user"], user.options["user"]), ("AGILE\\svc-reader", "AGILE\\jdoe"))
        self.assertEqual(profile["groups"], ["Domain Users", "Report Users", "Scheduler Users", "docker-users"])
        self.assertEqual(user.searches, [])  # the user's own connection only proves the password
        self.assert_all_unbound()

    def test_service_account_simple_mode_binds_as_user_dn(self):
        self.service(ldap_auth_method="SIMPLE", ldap_bind_dn="CN=svc,DC=agile,DC=local", ldap_bind_password="svc-pass").authenticate(
            "jdoe", "jdoe-pass"
        )
        self.assertEqual(self.directory.connections[1].options["user"], JDOE_DN)

    def test_service_account_errors(self):
        settings = {"ldap_bind_dn": "AGILE\\svc-reader", "ldap_bind_password": "svc-pass"}
        with self.assertRaises(InvalidCredentialsError):
            self.service(**settings).authenticate("nobody", "x")
        with self.assertRaises(InvalidCredentialsError):
            self.service(**settings).authenticate("jdoe", "wrong")
        with self.assertRaises(AuthenticationUnavailableError):
            self.service(ldap_bind_dn="AGILE\\svc-reader", ldap_bind_password="wrong").authenticate("jdoe", "jdoe-pass")
        self.assert_all_unbound()

    def test_insecure_transport_is_refused_before_connecting(self):
        for changes in ({"ldap_start_tls": False}, {"ldap_start_tls": False, "ldap_auth_method": "SIMPLE"},
                        {"ldap_start_tls": False, "ldap_ntlm_session_encryption": False}):
            with self.subTest(changes), self.assertRaises(AuthenticationUnavailableError) as raised:
                self.service(**changes).authenticate("jdoe", "jdoe-pass")
            self.assertEqual(str(raised.exception), "Secure LDAP must be enabled.")
        self.connection_class.assert_not_called()

    def test_ntlm_session_encryption_is_used_only_when_ldap3_supports_it(self):
        with patch("app.services.ldap_service.ntlm_session_encryption_supported", return_value=True), patch(
            "ldap3.ENCRYPT", "ENCRYPT", create=True
        ):
            self.service(ldap_start_tls=False).authenticate("jdoe", "jdoe-pass")
        connection = self.directory.connections[0]
        self.assertEqual(connection.options["session_security"], "ENCRYPT")
        self.assertNotIn("start_tls", connection.calls)

    def test_ntlm_configuration_errors(self):
        cases = [({"ldap_netbios_domain": ""}, "NTLM requires LDAP_NETBIOS_DOMAIN."),
                 ({"ldap_auth_method": "KERBEROS"}, "LDAP_AUTH_METHOD must be SIMPLE or NTLM.")]
        for changes, message in cases:
            with self.subTest(changes), self.assertRaises(AuthenticationUnavailableError) as raised:
                self.service(**changes).authenticate("jdoe", "jdoe-pass")
            self.assertEqual(str(raised.exception), message)
        with patch("app.services.ldap_service.md4_available", return_value=False), self.assertRaises(AuthenticationUnavailableError):
            self.service().authenticate("jdoe", "jdoe-pass")

    def test_missing_configuration_is_unavailable(self):
        for changes in ({"ldap_enabled": False}, {"ldap_host": ""}, {"ldap_base_dn": ""}):
            with self.subTest(changes), self.assertRaises(AuthenticationUnavailableError):
                self.service(**changes).authenticate("jdoe", "jdoe-pass")

    def test_tls_requires_certificate_validation(self):
        with patch("app.services.ldap_service.Tls") as tls:
            self.service(ldap_ca_cert_file="/path/ca.pem").authenticate("jdoe", "jdoe-pass")
        self.assertEqual(tls.call_args.kwargs["validate"], ssl.CERT_REQUIRED)
        self.assertEqual(tls.call_args.kwargs["ca_certs_file"], "/path/ca.pem")

    def test_binary_object_sid_resolves_primary_group(self):
        raw = bytes([1, 5, 0, 0, 0, 0, 0, 5]) + b"".join(n.to_bytes(4, "little") for n in (21, 1111, 2222, 3333, 1105))
        self.assertEqual(sid_to_string(raw), f"{DOMAIN_SID}-1105")
        self.directory.users["jdoe"]._attributes["objectSid"] = [raw]
        self.assertIn("Domain Users", self.service().authenticate("jdoe", "jdoe-pass")["groups"])


class LiveCheckScriptTests(LdapServiceTests.__base__):
    """Runs scripts/ldap_live_check.py --authenticate against the fake directory (no network)."""

    def setUp(self):
        import importlib.util
        import io

        spec = importlib.util.spec_from_file_location("ldap_live_check", Path(__file__).resolve().parents[1] / "scripts" / "ldap_live_check.py")
        self.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.script)
        self.directory = FakeActiveDirectory()
        for target in (patch("app.services.ldap_service.Connection", side_effect=self.directory.connect),
                       patch("app.services.ldap_service.Server"), patch("app.services.ldap_service.md4_available", return_value=True)):
            target.start()
            self.addCleanup(target.stop)
        self.output = io.StringIO()

    def run_check(self, username, password):
        from contextlib import redirect_stdout

        with patch.dict(os.environ, {"LDAP_TEST_USERNAME": username, "LDAP_TEST_PASSWORD": password}), redirect_stdout(self.output):
            return self.script.authenticate(make_settings(**AGILE))

    def test_one_attempt_reports_profile_and_reference_groups_without_secrets(self):
        self.assertEqual(self.run_check("AGILE\\jdoe", "jdoe-pass"), 0)
        text = self.output.getvalue()
        self.assertNotIn("jdoe-pass", text)
        self.assertIn("RESULT: authenticated", text)
        self.assertRegex(text, r"group 'Report Users'\s+exists\s+member")
        self.assertRegex(text, r"group 'Domain Admins'\s+exists\s+not a member")
        self.assertNotIn("Administrator", text)  # no member lists
        self.assertEqual(len(self.directory.connections), 1)  # exactly one bind

    def test_failure_output_redacts_password(self):
        self.directory.raise_on_bind = __import__("ldap3").core.exceptions.LDAPSocketOpenError("error near s3cr3t-value")
        self.assertEqual(self.run_check("jdoe", "s3cr3t-value"), 1)
        self.assertNotIn("s3cr3t-value", self.output.getvalue())


class NtlmCompatibilityTests(unittest.TestCase):
    def test_md4_is_available_for_ldap3_ntlm(self):
        """OpenSSL 3 disables MD4; pycryptodome must provide it or every NTLM bind fails."""
        from ldap3.utils.ntlm import NtlmClient

        self.assertTrue(md4_available())
        client = NtlmClient("AGILE", "jdoe", "test-only-password")
        self.assertEqual(len(client.ntowf_v2()), 16)

    def test_installed_ldap3_session_encryption_capability_is_detected(self):
        import inspect

        from ldap3 import Connection

        self.assertEqual(ntlm_session_encryption_supported(), "session_security" in inspect.signature(Connection.__init__).parameters)


class GroupAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def login(self, groups, **settings):
        settings = make_settings(**settings)

        class Directory(FakeLdap):
            def authenticate(self, username, password):
                return {**super().authenticate(username, password), "groups": groups}

        service = AuthService(ldap=Directory(), repository=UserRepository(), limiter=LoginRateLimiter(settings), authorizer=GroupAuthorizer(settings))
        return service.login(self.db, "person", "secret")

    def test_any_authenticated_user_is_allowed_when_no_groups_are_configured(self):
        user = self.login([])
        self.assertEqual((user.username, user.permissions), ("person", None))

    def test_allowed_groups_are_enforced_case_insensitively(self):
        self.assertEqual(self.login(["report users"], ldap_allowed_groups="Report Users;Scheduler Users").username, "person")
        with self.assertRaises(AuthorizationDeniedError):
            self.login(["Domain Admins", "docker-users"], ldap_allowed_groups="Report Users")
        self.assertEqual(self.db.query(User).count(), 1)  # the denied login did not create or update anyone

    def test_permissions_come_only_from_configured_mappings(self):
        mapping = "Report Users=reports:read,reports:write;Scheduler Users=scheduler:run;Empty="
        user = self.login(["Report Users", "Domain Admins", "Unknown Group"], ldap_group_permissions=mapping)
        self.assertEqual(user.permissions, "reports:read,reports:write")
        user = self.login(["Domain Admins"], ldap_group_permissions=mapping)
        self.assertIsNone(user.permissions)  # Domain Admins grants nothing unless explicitly mapped

    def test_group_names_are_not_persisted(self):
        self.login(["Report Users", "Domain Admins"])
        self.assertFalse(any("group" in column.name for column in User.__table__.columns))

    def test_rate_limit_is_shared_across_username_formats(self):
        limiter = LoginRateLimiter(make_settings(login_max_attempts=2, login_window_seconds=60))
        service = AuthService(ldap=LdapService(make_settings(**AGILE)), limiter=limiter)
        for name in ("AGILE\\jdoe", "jdoe@agile.local"):
            limiter.check(service._limit_key(name))
        with self.assertRaises(LoginRateLimitedError):
            limiter.check(service._limit_key("JDOE"))


@unittest.skipUnless(shutil.which("openssl"), "openssl CLI is required to create throwaway certificates")
class LdapRealSocketTests(unittest.TestCase):
    """Uses real local sockets (no mocks) to prove TLS verification and timeouts fail safely."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ca = cls.path("ca.pem")
        cls.openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=Test CA",
                    "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign",
                    "-keyout", cls.path("ca.key"), "-out", cls.ca)
        for name, san in (("matching", "DNS:localhost"), ("mismatched", "DNS:wrong-host.test")):
            with open(cls.path(f"{name}.ext"), "w") as ext:
                # Python's strict X.509 verification requires the key identifier extensions.
                ext.write(f"subjectAltName={san}\nauthorityKeyIdentifier=keyid\nsubjectKeyIdentifier=hash\nbasicConstraints=CA:FALSE\n")
            cls.openssl("req", "-newkey", "rsa:2048", "-nodes", "-subj", f"/CN={name}",
                        "-keyout", cls.path(f"{name}.key"), "-out", cls.path(f"{name}.csr"))
            cls.openssl("x509", "-req", "-in", cls.path(f"{name}.csr"), "-CA", cls.ca, "-CAkey", cls.path("ca.key"),
                        "-CAcreateserial", "-days", "1", "-extfile", cls.path(f"{name}.ext"), "-out", cls.path(f"{name}.pem"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def path(cls, name):
        return os.path.join(cls.tmp.name, name)

    @staticmethod
    def openssl(*args):
        subprocess.run(["openssl", *args], check=True, capture_output=True)

    def serve(self, certificate: str | None):
        """Accepts one connection, optionally completes TLS, then never sends an LDAP response."""
        listener = socket.create_server(("127.0.0.1", 0))
        listener.settimeout(10)
        context = None
        if certificate:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(self.path(f"{certificate}.pem"), self.path(f"{certificate}.key"))

        def accept():
            try:
                client, _ = listener.accept()
                with client:
                    if context:
                        try:
                            context.wrap_socket(client, server_side=True)
                        except (ssl.SSLError, OSError):
                            return
                    time.sleep(4)
            except OSError:
                pass

        threading.Thread(target=accept, daemon=True).start()
        self.addCleanup(listener.close)
        return listener.getsockname()[1]

    def authenticate(self, port, **changes):
        values = {
            "ldap_enabled": True, "ldap_host": "127.0.0.1", "ldap_port": port, "ldap_base_dn": "DC=example,DC=test",
            "ldap_domain": "example.test", "ldap_use_ssl": True, "ldap_connect_timeout_seconds": 2,
            "ldap_search_timeout_seconds": 2,
        }
        values.update(changes)
        started = time.monotonic()
        with self.assertRaises(AuthenticationUnavailableError) as raised:
            LdapService(make_settings(**values)).authenticate("person", "secret")
        self.assertEqual(str(raised.exception), "LDAP service is unavailable.")
        return str(raised.exception.__cause__), time.monotonic() - started

    def test_certificate_from_untrusted_ca_is_rejected(self):
        cause, _ = self.authenticate(self.serve("matching"), ldap_host="localhost")
        self.assertIn("CERTIFICATE_VERIFY_FAILED", cause)

    def test_trusted_ca_with_mismatched_hostname_is_rejected(self):
        cause, _ = self.authenticate(self.serve("mismatched"), ldap_ca_cert_file=self.ca)
        self.assertNotIn("CERTIFICATE_VERIFY_FAILED", cause)
        self.assertIn("doesn't match", cause)

    def test_trusted_ca_and_matching_hostname_completes_tls(self):
        # Positive control: TLS succeeds, so the only failure left is the silent server timing out.
        # ldap3 matches DNS names only, so LDAP_HOST must be a hostname rather than an IP address.
        cause, elapsed = self.authenticate(self.serve("matching"), ldap_host="localhost", ldap_ca_cert_file=self.ca)
        self.assertNotIn("CERTIFICATE", cause.upper())
        self.assertLess(elapsed, 4)

    def test_connection_refused_is_unavailable(self):
        with socket.create_server(("127.0.0.1", 0)) as probe:
            port = probe.getsockname()[1]
        _, elapsed = self.authenticate(port)
        self.assertLess(elapsed, 4)

    def test_silent_server_times_out_during_ldaps_handshake(self):
        cause, elapsed = self.authenticate(self.serve(None))
        self.assertIn("timed out", cause)
        self.assertLess(elapsed, 4)

    def test_silent_server_times_out_during_start_tls(self):
        _, elapsed = self.authenticate(self.serve(None), ldap_use_ssl=False, ldap_start_tls=True)
        self.assertLess(elapsed, 4)


class JwtTests(unittest.TestCase):
    def test_token_generation_validation_and_expiration(self):
        settings = make_settings(jwt_secret_key="test-secret-that-is-long-enough-for-unit-tests")
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="")
        with patch("app.utils.security.get_settings", return_value=settings):
            credentials.credentials = create_access_token("person")
            self.assertEqual(get_token_subject(credentials), "person")
            expired = jwt.encode(
                {"sub": "person", "exp": datetime.now(UTC) - timedelta(seconds=1)},
                settings.jwt_secret_key,
                algorithm=settings.jwt_algorithm,
            )
            with self.assertRaises(Exception):
                get_token_subject(HTTPAuthorizationCredentials(scheme="Bearer", credentials=expired))


if __name__ == "__main__":
    unittest.main()
