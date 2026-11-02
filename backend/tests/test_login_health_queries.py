"""Login and health use numbered SQL while retaining model and API contracts."""
from datetime import datetime
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.sql.selectable import TextualSelect

from app.database.base import Base
from app.repositories.user_repository import UserRepository
from app.routes.health import database_health_check, health_check
from app.utils.query_store import QueryStore, query_store


class LoginHealthQueryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.repository = UserRepository()
        self.statements = []
        event.listen(self.engine, "before_cursor_execute", self.capture)

    def capture(self, connection, cursor, sql, params, context, many):
        self.statements.append(context.compiled.statement if context.compiled else None)

    def assert_catalog_execution(self):
        self.assertTrue(self.statements)
        self.assertTrue(all(isinstance(statement, (TextClause, TextualSelect)) for statement in self.statements),
                        [type(statement).__name__ for statement in self.statements])
        self.assertFalse(self.db.new)
        self.assertFalse(self.db.dirty)

    def test_insert_update_preserves_identity_types_and_database_defaults(self):
        first = self.repository.upsert_from_ldap(self.db, {"username": "person", "title": "Analyst", "full_name": "ಹೆಸರು ✓"})
        user_id = first.id
        created_at = first.created_at
        self.assertIsInstance(first.created_at, datetime)
        self.assertIsInstance(first.updated_at, datetime)
        second = self.repository.upsert_from_ldap(self.db, {"username": "person", "title": "Manager", "permissions": ["reports:read"]})
        self.assertIs(first, second)
        self.assertEqual(second.id, user_id)
        self.assertEqual(second.created_at, created_at)
        self.assertEqual(second.title, "Manager")
        self.assertIsNone(second.full_name)
        self.assertEqual(second.permissions, "reports:read")
        self.assertIs(second.is_active, True)
        self.assert_catalog_execution()

    def test_unchanged_profile_does_not_issue_an_update(self):
        profile = {"username": "same", "full_name": "Same User"}
        user = self.repository.upsert_from_ldap(self.db, profile)
        updated_at = user.updated_at
        self.statements.clear()
        self.repository.upsert_from_ldap(self.db, profile)
        self.assertEqual(len(self.statements), 2)
        self.assertEqual(user.updated_at, updated_at)
        self.assert_catalog_execution()

    def test_username_is_bound_as_a_value(self):
        username = "name' OR 1=1 --"
        user = self.repository.upsert_from_ldap(self.db, {"username": username})
        self.assertEqual(user.username, username)
        self.assertIsNone(self.repository.get_by_username(self.db, "different"))
        self.assert_catalog_execution()

    def test_unique_email_error_can_be_rolled_back(self):
        self.repository.upsert_from_ldap(self.db, {"username": "first", "email": "shared@example.test"})
        self.repository.upsert_from_ldap(self.db, {"username": "second", "email": "other@example.test"})
        with self.assertRaises(IntegrityError):
            self.repository.upsert_from_ldap(self.db, {"username": "second", "email": "shared@example.test"})
        self.db.rollback()
        self.assertEqual(self.repository.get_by_username(self.db, "second").email, "other@example.test")
        self.assert_catalog_execution()

    def test_health_contract_and_query_file_failure(self):
        self.assertEqual(health_check(), {"status": "ok"})
        self.assertEqual(database_health_check(self.db), {"status": "ok", "database": "reachable"})
        with patch.object(query_store, "get", side_effect=FileNotFoundError("private path")):
            with self.assertRaises(HTTPException) as raised:
                database_health_check(self.db)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail, "Database is unavailable.")
        self.assert_catalog_execution()


class NumberedQueryStoreTests(unittest.TestCase):
    def test_number_lookup_accepts_integer_and_string(self):
        self.assertEqual(query_store.get(1), query_store.get("1"))

    def test_reload_and_duplicate_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queries.txt"
            path.write_text("-- 1: First\n" + query_store.get("1"), encoding="utf-8")
            store = QueryStore(path)
            self.assertEqual(store.get(1), query_store.get("1"))
            path.write_text("-- 1: Changed\n" + query_store.get("5"), encoding="utf-8")
            self.assertEqual(store.get(1), query_store.get("5"))
        with self.assertRaisesRegex(ValueError, "defined more than once"):
            QueryStore._parse("-- 1: First\n" + query_store.get("1") + "\n-- 1: Duplicate\n" + query_store.get("1"))
