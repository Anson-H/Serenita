import os
import tempfile
import unittest
from pathlib import Path


class ConversationStoragePathTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["SERENITA_DATA_ROOT"] = self.tempdir.name
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()
        os.environ.pop("SERENITA_DATA_ROOT", None)

    def test_new_sessions_store_timeline_directly_under_sessions_directory(self):
        from backend.app.repositories.conversation_repository import ConversationRepository

        repository = ConversationRepository()

        session_id = repository.ensure_session("demo_patient")

        row = repository.session_row("demo_patient", session_id)
        self.assertEqual(row["timeline_path"], f"conversations/sessions/{session_id}.jsonl")
        self.assertTrue(
            (self.root / "demo_patient" / "conversations" / "sessions").is_dir()
        )
        self.assertEqual(
            list((self.root / "demo_patient" / "conversations" / "sessions").glob("*/")),
            [],
        )

    def test_dated_timeline_paths_are_flattened_during_init(self):
        from backend.app.repositories.conversation_repository import ConversationRepository
        from backend.app.storage.paths import app_paths
        from backend.app.storage.sqlite import connect

        repository = ConversationRepository()
        repository.init_db("demo_patient")

        session_id = "dated-session"
        timestamp = "2026-05-24T00:00:00Z"
        dated_relative_path = f"conversations/sessions/2026-05-23/{session_id}.jsonl"
        dated_path = self.root / "demo_patient" / dated_relative_path
        dated_path.parent.mkdir(parents=True, exist_ok=True)
        dated_path.write_text('{"type": "user_message"}\n', encoding="utf-8")

        with connect(app_paths().conversations_db("demo_patient")) as connection:
            connection.execute(
                """
                INSERT INTO conversation_sessions (
                    session_id, account, title, timeline_path, created_at,
                    last_active_at, last_message_preview, active_path_message_ids
                )
                VALUES (?, ?, ?, ?, ?, ?, '', '[]')
                """,
                (
                    session_id,
                    "demo_patient",
                    "旧会话",
                    dated_relative_path,
                    timestamp,
                    timestamp,
                ),
            )

        repository.init_db("demo_patient")

        row = repository.session_row("demo_patient", session_id)
        flattened_relative_path = f"conversations/sessions/{session_id}.jsonl"
        self.assertEqual(row["timeline_path"], flattened_relative_path)
        self.assertFalse(dated_path.exists())
        self.assertTrue((self.root / "demo_patient" / flattened_relative_path).exists())
        self.assertFalse(dated_path.parent.exists())
