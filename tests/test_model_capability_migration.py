import os
import tempfile
import unittest

from backend.app.storage.sqlite import connect


class ModelCapabilityMigrationTests(unittest.TestCase):
    def test_create_app_migrates_all_existing_account_config_databases(self):
        with tempfile.TemporaryDirectory() as tempdir:
            os.environ["SERENITA_DATA_ROOT"] = tempdir
            try:
                for account in ("demo_patient", "other_patient"):
                    config_dir = os.path.join(tempdir, account, "config")
                    os.makedirs(config_dir, exist_ok=True)
                    config_db = os.path.join(config_dir, "config.db")
                    with connect(config_db) as connection:
                        connection.execute(
                            """
                            CREATE TABLE models (
                                model_id TEXT PRIMARY KEY,
                                provider_id TEXT NOT NULL,
                                remote_model_id TEXT NOT NULL,
                                model_name TEXT NOT NULL,
                                capabilities_json TEXT NOT NULL,
                                created_at TEXT NOT NULL,
                                updated_at TEXT NOT NULL
                            )
                            """
                        )
                        connection.execute(
                            """
                            INSERT INTO models (
                                model_id, provider_id, remote_model_id, model_name,
                                capabilities_json, created_at, updated_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                f"{account}:legacy-model",
                                "fake",
                                "legacy-model",
                                "Legacy Model",
                                '{"text": true, "vision": true, "file_mime_types": ["image/png"], "thinking_modes": ["default", "high"]}',
                                "2026-05-22T00:00:00+00:00",
                                "2026-05-22T00:00:00+00:00",
                            ),
                        )
                        connection.execute(
                            """
                            CREATE TABLE model_default_settings (
                                setting_key TEXT PRIMARY KEY,
                                model_id TEXT,
                                created_at TEXT NOT NULL,
                                updated_at TEXT NOT NULL,
                                CHECK (setting_key IN ('chat', 'title', 'ocr', 'compact')),
                                FOREIGN KEY (model_id) REFERENCES models(model_id) ON DELETE SET NULL
                            )
                            """
                        )
                        connection.execute(
                            """
                            INSERT INTO model_default_settings (
                                setting_key, model_id, created_at, updated_at
                            )
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                "chat",
                                f"{account}:legacy-model",
                                "2026-05-22T00:00:00+00:00",
                                "2026-05-22T00:00:00+00:00",
                            ),
                        )

                from backend.app.main import create_app

                create_app()

                for account in ("demo_patient", "other_patient"):
                    config_db = os.path.join(tempdir, account, "config", "config.db")
                    with connect(config_db) as connection:
                        columns = {
                            row["name"]
                            for row in connection.execute("PRAGMA table_info(models)").fetchall()
                        }
                        row = connection.execute(
                            "SELECT file_mime_types, thinking_modes FROM models"
                        ).fetchone()
                        default_foreign_keys = connection.execute(
                            "PRAGMA foreign_key_list(model_default_settings)"
                        ).fetchall()
                        default_row = connection.execute(
                            "SELECT model_id FROM model_default_settings WHERE setting_key = 'chat'"
                        ).fetchone()
                        connection.execute(
                            """
                            INSERT INTO model_default_settings (
                                setting_key, model_id, created_at, updated_at
                            )
                            VALUES ('vision_parse', ?, '2026-05-22T00:00:00+00:00', '2026-05-22T00:00:00+00:00')
                            """,
                            (f"{account}:legacy-model",),
                        )
                        connection.execute(
                            """
                            INSERT INTO model_default_settings (
                                setting_key, model_id, created_at, updated_at
                            )
                            VALUES ('title', ?, '2026-05-22T00:00:00+00:00', '2026-05-22T00:00:00+00:00')
                            """,
                            (f"{account}:legacy-model",),
                        )
                    self.assertNotIn("capabilities_json", columns)
                    self.assertNotIn("supports_file_input", columns)
                    self.assertNotIn("supports_vision", columns)
                    self.assertIn("supports_text", columns)
                    self.assertEqual(row["file_mime_types"], "image/png")
                    self.assertEqual(row["thinking_modes"], "default\nhigh")
                    self.assertEqual(default_foreign_keys[0]["table"], "models")
                    self.assertEqual(default_row["model_id"], f"{account}:legacy-model")
            finally:
                os.environ.pop("SERENITA_DATA_ROOT", None)


if __name__ == "__main__":
    unittest.main()
