import errno
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from member_support import account_id as account_id_for, member_id


class StoragePathTests(unittest.TestCase):
    account_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

    @staticmethod
    def mode(path: Path) -> int:
        return stat.S_IMODE(path.stat().st_mode)

    def test_default_data_root_is_project_serenita_files_directory(self):
        from backend.app.storage.paths import data_root

        original = os.environ.pop("DATA_ROOT", None)
        try:
            expected_root = Path(__file__).resolve().parents[1] / "serenita_files"

            self.assertEqual(data_root(), expected_root)
            self.assertNotEqual(data_root(), Path(tempfile.gettempdir()) / "serenita_files")
        finally:
            if original is not None:
                os.environ["DATA_ROOT"] = original

    def test_data_root_can_still_be_overridden_for_tests_or_deployments(self):
        from backend.app.storage.paths import data_root

        original = os.environ.get("DATA_ROOT")
        try:
            os.environ["DATA_ROOT"] = "/tmp/custom-serenita-root"

            self.assertEqual(data_root(), Path("/tmp/custom-serenita-root"))
        finally:
            if original is None:
                os.environ.pop("DATA_ROOT", None)
            else:
                os.environ["DATA_ROOT"] = original

    def test_auth_and_account_storage_paths_use_final_names(self):
        from backend.app.storage.paths import AppPaths

        paths = AppPaths(Path("/tmp/serenita-root"))

        self.assertEqual(paths.auth_db, Path("/tmp/serenita-root/all_users/auth/auth.db"))
        self.assertEqual(
            paths.account_root(self.account_id),
            Path(f"/tmp/serenita-root/accounts/{self.account_id}"),
        )
        self.assertEqual(
            paths.members_db(self.account_id),
            Path(
                f"/tmp/serenita-root/accounts/{self.account_id}/members/db_storage/members.db"
            ),
        )
        self.assertEqual(
            paths.config_db(self.account_id),
            Path(
                f"/tmp/serenita-root/accounts/{self.account_id}/config/settings.db"
            ),
        )
        self.assertEqual(
            paths.conversations_db(self.account_id),
            Path(
                f"/tmp/serenita-root/accounts/{self.account_id}/conversations/db_storage/conversations.db"
            ),
        )
        self.assertEqual(
            paths.report_attachment_path(
                self.account_id, "RESOURCE-0123456789ABCDEF", "pdf"
            ),
            Path(
                f"/tmp/serenita-root/accounts/{self.account_id}/reports/attachments/RESOURCE-0123456789ABCDEF.pdf"
            ),
        )
        self.assertEqual(
            paths.provider_master_key,
            Path("/tmp/serenita-root/all_users/secrets/provider_master.key"),
        )

    def test_sqlite_context_manager_closes_connection_after_use(self):
        from backend.app.storage.sqlite import connect

        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "nested" / "test.db"

            with connect(db_path) as connection:
                connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")

            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")

    def test_sqlite_context_manager_accepts_string_paths(self):
        from backend.app.storage.sqlite import connect

        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "nested" / "test.db")

            with connect(db_path) as connection:
                connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
                connection.execute("INSERT INTO sample (id) VALUES (1)")

            with connect(db_path) as connection:
                row = connection.execute("SELECT id FROM sample").fetchone()

            self.assertEqual(row["id"], 1)

    def test_sqlite_database_parent_and_sidecars_are_private(self):
        from backend.app.storage.sqlite import _secure_sqlite_files, connect

        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "account" / "config" / "settings.db"
            db_path.parent.mkdir(parents=True, mode=0o755)
            db_path.parent.chmod(0o755)

            with connect(db_path) as connection:
                connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")

            self.assertEqual(self.mode(db_path.parent), 0o700)
            self.assertEqual(self.mode(db_path), 0o600)

            for suffix in ("-wal", "-shm", "-journal"):
                sidecar = db_path.with_name(f"{db_path.name}{suffix}")
                sidecar.write_bytes(b"test-sidecar")
                sidecar.chmod(0o644)
            _secure_sqlite_files(db_path)

            for suffix in ("-wal", "-shm", "-journal"):
                self.assertEqual(
                    self.mode(db_path.with_name(f"{db_path.name}{suffix}")),
                    0o600,
                )

    def test_private_file_ignores_disappearing_sqlite_sidecar(self):
        from backend.app.storage.paths import ensure_private_file

        journal = Path("/tmp/serenita-racing.db-journal")
        with (
            patch.object(Path, "lstat", return_value=os.stat_result((stat.S_IFREG | 0o644,) + (0,) * 9)),
            patch.object(
                Path,
                "chmod",
                side_effect=FileNotFoundError(
                    errno.ENOENT,
                    os.strerror(errno.ENOENT),
                    str(journal),
                ),
            ),
        ):
            self.assertEqual(ensure_private_file(journal), journal)

    def test_private_file_does_not_hide_permission_errors(self):
        from backend.app.storage.paths import ensure_private_file

        database = Path("/tmp/serenita-private.db")
        with (
            patch.object(Path, "lstat", return_value=os.stat_result((stat.S_IFREG | 0o644,) + (0,) * 9)),
            patch.object(
                Path,
                "chmod",
                side_effect=PermissionError(
                    errno.EACCES,
                    os.strerror(errno.EACCES),
                    str(database),
                ),
            ),
            self.assertRaises(PermissionError),
        ):
            ensure_private_file(database)

    def test_account_tree_first_access_hardens_current_id_tree(self):
        from backend.app.storage.paths import AppPaths

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "serenita_files"
            account_root = root / "accounts" / self.account_id
            attachment_dir = account_root / "conversations" / "attachments" / "session"
            attachment_dir.mkdir(parents=True, mode=0o755)
            attachment_path = attachment_dir / "scan.pdf"
            attachment_path.write_bytes(b"private")
            for path in (root, account_root, account_root / "conversations", attachment_dir):
                path.chmod(0o755)
            attachment_path.chmod(0o644)

            paths = AppPaths(root)
            self.assertEqual(paths.account_root(self.account_id), account_root)

            for path in (root, account_root, account_root / "conversations", attachment_dir):
                self.assertEqual(self.mode(path), 0o700)
            self.assertEqual(self.mode(attachment_path), 0o600)

    def test_account_paths_reject_login_names_noncanonical_ids_and_traversal(self):
        from backend.app.storage.paths import AppPaths

        paths = AppPaths(Path("/tmp/serenita-root"))
        for value in (
            "demo_patient",
            "../escape",
            self.account_id.upper(),
            self.account_id.replace("-", ""),
        ):
            with self.assertRaises(ValueError):
                paths.account_root(value)

    def test_session_persistence_uses_private_permissions(self):
        from backend.app.storage.session_persistence import JsonlSessionPersistence
        from backend.app.storage.paths import AppPaths
        from backend.app.domain.conversations.events import SessionHeader, make_event

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DATA_ROOT": directory}):
            paths = AppPaths(Path(directory))
            persistence = JsonlSessionPersistence()
            header = SessionHeader(id="session", created_at=1, account_id=self.account_id)
            persistence.create(header)
            timeline_path = paths.account_root(self.account_id) / "conversations" / "sessions" / "session.jsonl"
            self.assertEqual(self.mode(timeline_path.parent), 0o700)
            self.assertEqual(self.mode(timeline_path), 0o600)
            persistence.append(self.account_id, "session", [make_event("workflow/trace", seq=0, data={"turn_id": "t", "payload": {}}, timestamp=2)], created_at=1)
            self.assertEqual(len(persistence.load(self.account_id, "session").events), 1)
            self.assertEqual(self.mode(timeline_path), 0o600)


class ConversationStoragePathTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["DATA_ROOT"] = self.tempdir.name
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()
        os.environ.pop("DATA_ROOT", None)

    def test_new_sessions_store_timeline_directly_under_sessions_directory(self):
        from backend.app.repositories.conversation_repository import ConversationRepository

        repository = ConversationRepository()

        account_id = account_id_for("demo_patient")
        session_id = repository.ensure_session(account_id, member_id=member_id("demo_patient"))

        row = repository.session_row(account_id, session_id)
        self.assertEqual(row["relative_path"], f"conversations/sessions/{session_id}.jsonl")
        self.assertNotIn("last_message_preview", row.keys())
        self.assertTrue(
            (self.root / "accounts" / account_id / "conversations" / "sessions").is_dir()
        )
        self.assertEqual(
            list((self.root / "accounts" / account_id / "conversations" / "sessions").glob("*/")),
            [],
        )


    def test_attachment_name_is_safely_normalized(self):
        from backend.app.repositories.conversation_attachments import attachment_resource_id, normalize_attachment_name

        self.assertEqual(
            normalize_attachment_name(r"C:\fakepath\检验报告.pdf", ".pdf"),
            "检验报告.pdf",
        )
        self.assertEqual(normalize_attachment_name("../..", ".pdf"), "upload.pdf")
        self.assertEqual(
            normalize_attachment_name("e\u0301医疗报告\x00.pdf", ".pdf"),
            "é医疗报告.pdf",
        )
        self.assertLessEqual(
            len(normalize_attachment_name("检" * 200 + ".pdf", ".pdf").encode("utf-8")),
            180,
        )
        self.assertTrue(
            normalize_attachment_name("检" * 200 + ".pdf", ".pdf").endswith(".pdf")
        )
        long_name = normalize_attachment_name("检" * 200 + ".pdf", ".pdf")
        numbered_name = attachment_resource_id(long_name, 2)
        self.assertLessEqual(len(numbered_name.encode("utf-8")), 180)
        self.assertTrue(numbered_name.endswith("-002.pdf"))

    def test_conversation_resource_schema_rejects_invalid_states(self):
        from backend.app.repositories.conversation_repository import ConversationRepository
        from backend.app.storage.paths import app_paths
        from backend.app.storage.sqlite import connect

        repository = ConversationRepository()
        account_id = account_id_for("resource_states")
        session_id = repository.ensure_session(
            account_id,
            member_id=member_id("resource_states"),
        )

        invalid_states = [
            ("invalid-storage", "uploaded", "pending", None),
            ("invalid-lifecycle", "ready", "failed", "tomorrow"),
            ("writing-attached", "writing", "attached", None),
            ("writing-expiring", "writing", "pending", "tomorrow"),
            ("ready-pending-without-expiry", "ready", "pending", None),
        ]
        for resource_id, storage_status, lifecycle_status, expires_at in invalid_states:
            with self.subTest(resource_id=resource_id), self.assertRaises(
                sqlite3.IntegrityError
            ), connect(app_paths().conversations_db(account_id)) as connection:
                connection.execute(
                    """
                    INSERT INTO conversation_resources (
                        resource_id, session_id, original_filename, mime_type, size_bytes,
                        relative_path, sha256, storage_status, lifecycle_status,
                        expires_at, created_at, updated_at
                    ) VALUES (?, ?, 'invalid', 'image/jpeg', 1, ?, 'sha', ?, ?, ?,
                              'now', 'now')
                    """,
                    (
                        resource_id,
                        session_id,
                        f"conversations/attachments/{resource_id}",
                        storage_status,
                        lifecycle_status,
                        expires_at,
                    ),
                )


    def test_index_path_mismatch_is_rejected_without_rewriting_data(self):
        from backend.app.repositories.conversation_repository import ConversationRepository
        from backend.app.domain.conversations.events import SessionEventCorruptionError
        from backend.app.storage.paths import app_paths
        from backend.app.storage.sqlite import connect

        repository = ConversationRepository()
        account_id = account_id_for("demo_patient")
        session_id = repository.ensure_session(account_id, member_id=member_id("demo_patient"))
        dated_relative_path = f"conversations/sessions/2026-05-23/{session_id}.jsonl"
        with connect(app_paths().conversations_db(account_id)) as connection:
            connection.execute(
                "UPDATE conversations SET relative_path = ? WHERE session_id = ?",
                (dated_relative_path, session_id),
            )

        with self.assertRaises(SessionEventCorruptionError):
            repository.session_events(account_id, session_id)
        row = repository.session_row(account_id, session_id)
        self.assertEqual(row["relative_path"], dated_relative_path)
