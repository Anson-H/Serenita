from member_support import member_access
import os
import json
import sqlite3
import tempfile
import unittest
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
from pathlib import Path
from tests.api_client import TestClient
from fastapi.testclient import TestClient as RawTestClient
from backend.app.main import create_app
from member_support import member_id


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.previous_data_root = os.environ.get("DATA_ROOT")
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["DATA_ROOT"] = self.tempdir.name

        from backend.app.storage.paths import data_root
        from backend.app.main import create_app

        self.client = TestClient(create_app())
        self.data_root = data_root()

    def tearDown(self):
        self.tempdir.cleanup()
        if self.previous_data_root is None:
            os.environ.pop("DATA_ROOT", None)
        else:
            os.environ["DATA_ROOT"] = self.previous_data_root

    def test_session_is_unauthenticated_without_token(self):
        response = self.client.get("/api/auth/session")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"authenticated": False})

    def test_local_frontend_cors_allows_cookie_credentials(self):
        response = self.client.options(
            "/api/auth/session",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://localhost:5173",
        )
        self.assertEqual(response.headers["access-control-allow-credentials"], "true")

    def test_sign_up_cookie_is_secure_and_restores_session(self):
        sign_up_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "demo_patient",
                "account_name": "陈女士",
                "password": "secret",
                "confirm_password": "secret",
            },
        )

        self.assertEqual(sign_up_response.status_code, 200)
        body = sign_up_response.json()
        self.assertEqual(body["account"], "demo_patient")
        self.assertEqual(body["account_name"], "陈女士")
        self.assertNotIn("session_token", body)
        self.assertTrue(body["expires_at"])
        set_cookie = sign_up_response.headers["set-cookie"].lower()
        self.assertIn("serenita_auth_session_token=", set_cookie)
        self.assertIn("httponly", set_cookie)
        self.assertIn("samesite=lax", set_cookie)

        session_response = self.client.get("/api/auth/session")

        self.assertEqual(
            session_response.json(),
            {
                "authenticated": True,
                "account": "demo_patient",
                "account_name": "陈女士",
                "expires_at": body["expires_at"],
                "account_id": body["account_id"],
            },
        )


    def test_auth_requests_reject_unknown_fields(self):
        sign_up = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "unexpected_user",
                "account_name": "当前名称",
                "unexpected_field": "额外内容",
                "password": "secret",
                "confirm_password": "secret",
            },
        )

        self.assertEqual(sign_up.status_code, 422)
        self.assertFalse((self.data_root / "accounts").exists())


    def test_auth_api_rejects_an_unexpected_unique_index(self):
        from backend.app.storage.auth_database import initialize_auth_database
        from backend.app.storage.paths import app_paths

        initialize_auth_database()
        path = app_paths().auth_db
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE UNIQUE INDEX unexpected_session_owner_unique "
                "ON login_sessions(account_id)"
            )

        response = self.client.get("/api/auth/session")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "UNSUPPORTED_SCHEMA")
        with sqlite3.connect(path) as connection:
            indexes = {
                row[1] for row in connection.execute("PRAGMA index_list(login_sessions)")
            }
        self.assertIn("unexpected_session_owner_unique", indexes)

    def test_sign_up_and_sign_in_set_persistent_standard_http_cookie(self):
        from backend.app.api.dependencies import SESSION_COOKIE_NAME
        from backend.app.application.auth_service import SESSION_TTL
        from backend.app.core.time import parse_local_datetime

        sign_up_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "persistent_patient",
                "account_name": "林女士",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        self.assertEqual(sign_up_response.status_code, 200)

        for response in (
            sign_up_response,
            self.client.post(
                "/api/auth/sign_in",
                json={"account": "persistent_patient", "password": "secret"},
            ),
        ):
            self.assertEqual(response.status_code, 200)
            parsed = SimpleCookie()
            parsed.load(response.headers["set-cookie"])
            morsel = parsed[SESSION_COOKIE_NAME]
            self.assertEqual(
                int(morsel["max-age"]),
                int(SESSION_TTL.total_seconds()),
            )
            cookie_expiry = parsedate_to_datetime(morsel["expires"])
            response_expiry = parse_local_datetime(
                response.json()["expires_at"]
            ).astimezone(cookie_expiry.tzinfo)
            self.assertLess(
                abs((cookie_expiry - response_expiry).total_seconds()),
                1,
            )
            cookie = next(
                item
                for item in self.client.cookies.jar
                if item.name == SESSION_COOKIE_NAME
            )
            self.assertIsNotNone(cookie.expires)
            self.assertGreater(cookie.expires, 0)

    def test_sign_in_and_sign_out_update_session_state(self):
        self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "demo_patient",
                "account_name": "陈女士",
                "password": "secret",
                "confirm_password": "secret",
            },
        )

        sign_in_response = self.client.post(
            "/api/auth/sign_in",
            json={"account": "demo_patient", "password": "secret"},
        )
        self.assertNotIn("session_token", sign_in_response.json())
        sign_out_response = self.client.post("/api/auth/sign_out")
        session_response = self.client.get("/api/auth/session")

        self.assertEqual(sign_out_response.status_code, 200)
        self.assertEqual(sign_out_response.json(), {"success": True, "message": "已退出登录"})
        self.assertEqual(session_response.json(), {"authenticated": False})

    def test_sign_in_rejects_bad_credentials(self):
        response = self.client.post(
            "/api/auth/sign_in",
            json={"account": "missing", "password": "secret"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"]["code"], "SIGN_IN_FAILED")

    def test_registration_rejects_invalid_duplicate_and_mismatched_inputs(self):
        invalid_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "../bad",
                "account_name": "Bad",
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
                "account_name": "Bad",
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
                "account_name": " ",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        self.assertEqual(blank_name_response.status_code, 400)
        self.assertEqual(blank_name_response.json()["detail"]["code"], "INVALID_REQUEST")

        spaced_name_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "spaced_name",
                "account_name": "陈 女士",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        self.assertEqual(spaced_name_response.status_code, 200)
        self.assertEqual(spaced_name_response.json()["account_name"], "陈 女士")
        self.client.post("/api/auth/sign_out")

        too_long_name_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "long_name",
                "account_name": "🙂" * 51,
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        self.assertEqual(too_long_name_response.status_code, 400)
        self.assertEqual(too_long_name_response.json()["detail"]["code"], "INVALID_REQUEST")

        blank_password_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "demo_patient",
                "account_name": "陈女士",
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
                "account_name": "陈女士",
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
                "account_name": "陈女士",
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
                "account_name": "陈女士",
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

    def test_account_update_accepts_unicode_display_name_with_internal_spaces(self):
        signed_up = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "demo_patient",
                "account_name": "陈女士",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        signed_up_session = signed_up.json()
        response = self.client.patch(
            "/api/auth/account",
            json={"account": "demo_patient", "account_name": "李 女士"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "authenticated": True,
                "account_id": signed_up_session["account_id"],
                "account": "demo_patient",
                "account_name": "李 女士",
                "expires_at": signed_up_session["expires_at"],
            },
        )

    def test_account_identifier_update_keeps_id_storage_credentials_and_session_stable(self):
        from backend.app.storage.favorite_database import initialize_favorites_database as _init_favorites_db
        from backend.app.storage.config_database import initialize_config_database
        from backend.app.storage.crypto import (
            seal_secret,
            seal_web_secret,
            unseal_secret,
            unseal_web_secret,
        )
        from backend.app.storage.paths import app_paths
        from backend.app.storage.sqlite import connect

        sign_up = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "demo_patient",
                "account_name": "陈女士",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        account_id = sign_up.json()["account_id"]
        original_cookie = self.client.cookies.get("serenita_auth_session_token")
        access = member_access("demo_patient")
        paths = app_paths()
        initialize_config_database(account_id)
        with connect(paths.config_db(account_id)) as connection:
            connection.execute(
                """
                INSERT INTO model_providers (
                    provider_id, provider_name, api_url, official_url,
                    encrypted_api_key, is_configured, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    "deepseek",
                    "DeepSeek",
                    "https://api.deepseek.com",
                    "https://deepseek.com",
                    seal_secret(account_id, "deepseek", "model-secret"),
                    "2026-01-01T00:00:00+08:00",
                    "2026-01-01T00:00:00+08:00",
                ),
            )
            connection.execute(
                """
                UPDATE web_providers
                SET encrypted_api_key = ?, is_configured = 1,
                    updated_at = ?
                WHERE provider_id = ?
                """,
                (
                    seal_web_secret(account_id, "exa", "web-secret"),
                    "2026-01-01T00:00:00+08:00",
                    "exa",
                ),
            )

        _init_favorites_db(account_id)
        with connect(paths.favorites_db(account_id)) as connection:
            connection.execute(
                """
                INSERT INTO favorites (
                    favorite_id, member_id, source_type, source_session_id, source_id,
                    title, content_snapshot, tags, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', ?, ?)
                """,
                (
                    "favorite-1",
                    access.member_id,
                    "message",
                    "session-1",
                    "message-1",
                    "收藏",
                    "内容",
                    "2026-01-01T00:00:00+08:00",
                    "2026-01-01T00:00:00+08:00",
                ),
            )

        timeline = (
            paths.account_root(account_id)
            / "conversations"
            / "sessions"
            / "session-1.jsonl"
        )
        timeline.write_text(
            json.dumps(
                {
                    "type": "session",
                    "version": 2,
                    "id": "session-1",
                    "accountId": account_id,
                    "createdAt": 1,
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

        with connect(paths.auth_db) as connection:
            sessions_before = [
                tuple(row)
                for row in connection.execute(
                    "SELECT * FROM login_sessions ORDER BY session_token_hash"
                ).fetchall()
            ]

        response = self.client.patch(
            "/api/auth/account",
            json={"account": "health_owner", "account_name": "李女士"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["account"], "health_owner")
        self.assertEqual(response.json()["account_name"], "李女士")
        self.assertEqual(response.json()["account_id"], account_id)
        self.assertTrue(paths.account_root(account_id).exists())
        self.assertEqual(
            {path.name for path in (paths.root / "accounts").iterdir()},
            {account_id},
        )
        self.assertEqual(
            self.client.cookies.get("serenita_auth_session_token"),
            original_cookie,
        )

        session_response = self.client.get("/api/auth/session")
        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(session_response.json()["account"], "health_owner")
        self.assertEqual(session_response.json()["account_name"], "李女士")

        with connect(paths.auth_db) as connection:
            sessions_after = [
                tuple(row)
                for row in connection.execute(
                    "SELECT * FROM login_sessions ORDER BY session_token_hash"
                ).fetchall()
            ]
        self.assertEqual(sessions_after, sessions_before)

        with connect(paths.favorites_db(account_id)) as connection:
            favorite = connection.execute(
                "SELECT favorite_id FROM favorites WHERE favorite_id = 'favorite-1'"
            ).fetchone()
            favorite_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(favorites)")
            }
        self.assertEqual(favorite["favorite_id"], "favorite-1")
        self.assertNotIn("account_id", favorite_columns)

        renamed_header = json.loads(
            (
                paths.account_root(account_id)
                / "conversations"
                / "sessions"
                / "session-1.jsonl"
            ).read_text(encoding="utf-8").splitlines()[0]
        )
        self.assertEqual(renamed_header["accountId"], account_id)

        with connect(paths.config_db(account_id)) as connection:
            model_row = connection.execute(
                "SELECT encrypted_api_key FROM model_providers WHERE provider_id = 'deepseek'"
            ).fetchone()
            web_row = connection.execute(
                "SELECT encrypted_api_key FROM web_providers WHERE provider_id = 'exa'"
            ).fetchone()
        self.assertEqual(
            unseal_secret(account_id, "deepseek", model_row["encrypted_api_key"]),
            "model-secret",
        )
        self.assertEqual(
            unseal_web_secret(account_id, "exa", web_row["encrypted_api_key"]),
            "web-secret",
        )

        self.client.post("/api/auth/sign_out")
        old_sign_in = self.client.post(
            "/api/auth/sign_in",
            json={"account": "demo_patient", "password": "secret"},
        )
        new_sign_in = self.client.post(
            "/api/auth/sign_in",
            json={"account": "health_owner", "password": "secret"},
        )
        self.assertEqual(old_sign_in.status_code, 401)
        self.assertEqual(new_sign_in.status_code, 200)

    def test_account_identifier_update_rejects_database_conflict_without_changes(self):
        self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "first_user",
                "account_name": "甲",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        self.client.post("/api/auth/sign_out")
        self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "second_user",
                "account_name": "乙",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        self.client.post("/api/auth/sign_out")
        self.client.post(
            "/api/auth/sign_in",
            json={"account": "first_user", "password": "secret"},
        )

        response = self.client.patch(
            "/api/auth/account",
            json={"account": "second_user", "account_name": "甲改"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "ACCOUNT_EXISTS")
        self.assertEqual(response.json()["detail"]["message"], "该用户标识已被使用。")
        session_response = self.client.get("/api/auth/session")
        self.assertEqual(session_response.json()["account"], "first_user")
        self.assertEqual(session_response.json()["account_name"], "甲")


def signup(client, account):
    response = client.post('/api/auth/sign_up', json={
        'account': account, 'account_name': account,
        'password': 'test-password', 'confirm_password': 'test-password',
    })
    assert response.status_code == 200
    return response.json()['account_id']


def test_mutations_and_logout_reject_the_previous_account():
    with RawTestClient(create_app()) as client:
        previous = signup(client, 'first')
        current = signup(client, 'second')
        for path, method in [('/api/auth/account', 'patch'), ('/api/auth/sign_out', 'post')]:
            response = getattr(client, method)(path, headers={'X-Serenita-Account-ID': previous},
                **({'json': {'account': 'second', 'account_name': 'wrong'}} if method == 'patch' else {}))
            assert response.status_code == 409
            assert response.json()['detail']['code'] == 'ACCOUNT_CONTEXT_CHANGED'
        assert client.get('/api/auth/session').json()['account_id'] == current
        missing = client.patch('/api/auth/account', json={'account': 'second', 'account_name': 'wrong'})
        assert missing.status_code == 422
        assert client.post('/api/auth/sign_out', headers={'X-Serenita-Account-ID': current}).status_code == 200
        assert client.post('/api/auth/sign_out').status_code == 200


def test_authenticated_api_responses_are_not_browser_cacheable():
    previous = os.environ.get("DATA_ROOT")
    directory = tempfile.TemporaryDirectory()
    os.environ["DATA_ROOT"] = directory.name
    try:
        from backend.app.main import create_app

        client = TestClient(create_app())
        client.post(
            "/api/auth/sign_up",
            json={
                "account": "cache_patient",
                "account_name": "缓存测试",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        response = client.get(f"/api/members/{member_id('cache_patient')}/reports")

        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["pragma"] == "no-cache"
    finally:
        directory.cleanup()
        if previous is None:
            os.environ.pop("DATA_ROOT", None)
        else:
            os.environ["DATA_ROOT"] = previous
