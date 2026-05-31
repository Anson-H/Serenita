import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


class StoragePathTests(unittest.TestCase):
    def test_default_data_root_is_project_serenita_files_directory(self):
        from backend.app.storage.paths import data_root

        original = os.environ.pop("SERENITA_DATA_ROOT", None)
        try:
            expected_root = Path(__file__).resolve().parents[1] / "serenita_files"

            self.assertEqual(data_root(), expected_root)
            self.assertNotEqual(data_root(), Path(tempfile.gettempdir()) / "serenita_files")
        finally:
            if original is not None:
                os.environ["SERENITA_DATA_ROOT"] = original

    def test_data_root_can_still_be_overridden_for_tests_or_deployments(self):
        from backend.app.storage.paths import data_root

        original = os.environ.get("SERENITA_DATA_ROOT")
        try:
            os.environ["SERENITA_DATA_ROOT"] = "/tmp/custom-serenita-root"

            self.assertEqual(data_root(), Path("/tmp/custom-serenita-root"))
        finally:
            if original is None:
                os.environ.pop("SERENITA_DATA_ROOT", None)
            else:
                os.environ["SERENITA_DATA_ROOT"] = original

    def test_auth_storage_paths_use_auth_names(self):
        from backend.app.storage.paths import AppPaths

        paths = AppPaths(Path("/tmp/serenita-root"))

        self.assertEqual(paths.auth_db, Path("/tmp/serenita-root/all_users/auth/auth_info.db"))
        self.assertEqual(
            paths.account_auth_dir("demo_patient"),
            Path("/tmp/serenita-root/all_users/auth/demo_patient"),
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
