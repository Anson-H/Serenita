import os
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    TestClient = None


@unittest.skipIf(TestClient is None, "FastAPI is installed in the uv environment")
class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.previous_data_root = os.environ.get("SERENITA_DATA_ROOT")
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["SERENITA_DATA_ROOT"] = self.tempdir.name

        from backend.app.api.auth import reset_auth_state_for_tests
        from backend.app.storage.paths import data_root
        from backend.app.main import create_app

        reset_auth_state_for_tests()
        self.client = TestClient(create_app())
        self.data_root = data_root()

    def tearDown(self):
        self.tempdir.cleanup()
        if self.previous_data_root is None:
            os.environ.pop("SERENITA_DATA_ROOT", None)
        else:
            os.environ["SERENITA_DATA_ROOT"] = self.previous_data_root

    def test_session_is_unauthenticated_without_token(self):
        response = self.client.get("/api/auth/session")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"authenticated": False})

    def test_sign_up_returns_token_that_restores_session(self):
        sign_up_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "demo_patient",
                "user_name": "陈女士",
                "password": "secret",
                "confirm_password": "secret",
            },
        )

        self.assertEqual(sign_up_response.status_code, 200)
        body = sign_up_response.json()
        self.assertEqual(body["account"], "demo_patient")
        self.assertEqual(body["user_name"], "陈女士")
        self.assertTrue(body["session_token"])
        self.assertTrue(body["expires_at"])

        session_response = self.client.get(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {body['session_token']}"},
        )

        self.assertEqual(
            session_response.json(),
            {
                "authenticated": True,
                "account": "demo_patient",
                "user_name": "陈女士",
                "expires_at": body["expires_at"],
            },
        )

    def test_sign_in_and_sign_out_update_session_state(self):
        self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "demo_patient",
                "user_name": "陈女士",
                "password": "secret",
                "confirm_password": "secret",
            },
        )

        sign_in_response = self.client.post(
            "/api/auth/sign_in",
            json={"account": "demo_patient", "password": "secret"},
        )
        token = sign_in_response.json()["session_token"]

        sign_out_response = self.client.post(
            "/api/auth/sign_out",
            headers={"Authorization": f"Bearer {token}"},
        )
        session_response = self.client.get(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(sign_out_response.status_code, 200)
        self.assertEqual(sign_out_response.json(), {"success": True, "message": "已 sign out"})
        self.assertEqual(session_response.json(), {"authenticated": False})

    def test_sign_in_rejects_bad_credentials(self):
        response = self.client.post(
            "/api/auth/sign_in",
            json={"account": "missing", "password": "secret"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"]["code"], "SIGN_IN_FAILED")

    def test_sign_in_migrates_legacy_login_storage_to_auth_storage(self):
        from backend.app.core.security import hash_secret
        from backend.app.storage.sqlite import connect

        legacy_db = self.data_root / "all_users" / "login" / "key_info.db"
        with connect(legacy_db) as connection:
            connection.execute(
                """
                CREATE TABLE login_accounts (
                    account TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    user_name TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO login_accounts(account, password_hash, user_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "legacy_patient",
                    hash_secret("secret"),
                    "旧用户",
                    "2026-05-21T00:00:00+00:00",
                    "2026-05-21T00:00:00+00:00",
                ),
            )
        (self.data_root / "all_users" / "login" / "legacy_patient").mkdir(parents=True)

        response = self.client.post(
            "/api/auth/sign_in",
            json={"account": "legacy_patient", "password": "secret"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(legacy_db.exists())
        self.assertTrue((self.data_root / "all_users" / "auth" / "auth_info.db").exists())
        self.assertTrue(
            (self.data_root / "all_users" / "auth" / "legacy_patient" / "session.json").exists()
        )

    def test_registration_rejects_invalid_duplicate_and_mismatched_inputs(self):
        invalid_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "../bad",
                "user_name": "Bad",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(invalid_response.json()["detail"]["code"], "INVALID_REQUEST")
        self.assertFalse(Path(self.data_root / "../bad").exists())

        too_long_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "a" * 21,
                "user_name": "Bad",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        self.assertEqual(too_long_response.status_code, 400)
        self.assertEqual(too_long_response.json()["detail"]["code"], "INVALID_REQUEST")

        blank_name_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "demo_patient",
                "user_name": " ",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        self.assertEqual(blank_name_response.status_code, 400)
        self.assertEqual(blank_name_response.json()["detail"]["code"], "INVALID_REQUEST")

        spaced_name_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "demo_patient",
                "user_name": "陈 女士",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        self.assertEqual(spaced_name_response.status_code, 400)
        self.assertEqual(spaced_name_response.json()["detail"]["code"], "INVALID_REQUEST")

        blank_password_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "demo_patient",
                "user_name": "陈女士",
                "password": "",
                "confirm_password": "",
            },
        )
        self.assertEqual(blank_password_response.status_code, 400)
        self.assertEqual(blank_password_response.json()["detail"]["code"], "INVALID_REQUEST")

        mismatch_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "demo_patient",
                "user_name": "陈女士",
                "password": "secret",
                "confirm_password": "different",
            },
        )
        self.assertEqual(mismatch_response.status_code, 400)
        self.assertEqual(mismatch_response.json()["detail"]["code"], "INVALID_REQUEST")

        created_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "Demo_Patient",
                "user_name": "陈女士",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        self.assertEqual(created_response.status_code, 200)
        self.assertEqual(created_response.json()["account"], "demo_patient")

        duplicate_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "demo_patient",
                "user_name": "陈女士",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        self.assertEqual(duplicate_response.status_code, 409)
        self.assertEqual(duplicate_response.json()["detail"]["code"], "ACCOUNT_EXISTS")

    def test_sign_in_rejects_invalid_account_and_empty_password_before_lookup(self):
        invalid_account_response = self.client.post(
            "/api/auth/sign_in",
            json={"account": "bad/account", "password": "secret"},
        )
        self.assertEqual(invalid_account_response.status_code, 400)
        self.assertEqual(invalid_account_response.json()["detail"]["code"], "INVALID_REQUEST")

        empty_password_response = self.client.post(
            "/api/auth/sign_in",
            json={"account": "demo_patient", "password": ""},
        )
        self.assertEqual(empty_password_response.status_code, 400)
        self.assertEqual(empty_password_response.json()["detail"]["code"], "INVALID_REQUEST")

    def test_account_update_rejects_user_name_with_spaces(self):
        sign_up_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "demo_patient",
                "user_name": "陈女士",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        token = sign_up_response.json()["session_token"]

        response = self.client.patch(
            "/api/auth/account",
            headers={"Authorization": f"Bearer {token}"},
            json={"user_name": "李 女士"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["code"], "INVALID_REQUEST")


if __name__ == "__main__":
    unittest.main()
