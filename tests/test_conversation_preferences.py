import sqlite3
from tests.api_client import TestClient
from backend.app.main import create_app
from backend.app.storage.paths import app_paths


DEFAULT_PREFERENCES = {
    "composer_submit_shortcut": "enter",
    "base_context_display_modes": {
        "system_prompt": "conversation_start",
        "tool_catalog": "conversation_start",
        "skill_catalog": "conversation_start",
        "runtime_context": "conversation_start",
    },
    "is_context_window_usage_visible": False,
    "is_related_content_visible": True,
    "is_token_usage_visible": False,
    "visible_context_types": [],
    "tool_display_types": ["model_tool_request", "tool_call"],
}


def _sign_up(client: TestClient, account: str) -> str:
    response = client.post(
        "/api/auth/sign_up",
        json={
            "account": account,
            "account_name": account,
            "password": "secret",
            "confirm_password": "secret",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["account_id"]


def test_conversation_preferences_persist_in_config_db_across_clients():
    app = create_app()
    first_browser = TestClient(app)
    account_id = _sign_up(first_browser, "alice")

    initial = first_browser.get("/api/account-settings/conversation-preferences")
    assert initial.status_code == 200
    assert initial.json() == DEFAULT_PREFERENCES

    updated = {
        "composer_submit_shortcut": "modifier_enter",
        "base_context_display_modes": {
            "system_prompt": "conversation_start",
            "tool_catalog": "turn_start",
            "skill_catalog": "hidden",
            "runtime_context": "every_step",
        },
        "is_context_window_usage_visible": True,
        "is_related_content_visible": False,
        "is_token_usage_visible": True,
        "visible_context_types": [
            "tool_observation",
            "current_user_message",
            "tool_observation",
        ],
        "tool_display_types": ["tool_call"],
    }
    saved = first_browser.put(
        "/api/account-settings/conversation-preferences",
        json=updated,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json() == {
        **updated,
        "visible_context_types": ["current_user_message", "tool_observation"],
    }

    second_browser = TestClient(app)
    signed_in = second_browser.post(
        "/api/auth/sign_in",
        json={"account": "alice", "password": "secret"},
    )
    assert signed_in.status_code == 200
    restored = second_browser.get("/api/account-settings/conversation-preferences")
    assert restored.status_code == 200
    assert restored.json() == saved.json()

    with sqlite3.connect(app_paths().config_db(account_id)) as connection:
        row = connection.execute(
            """
            SELECT composer_submit_shortcut, is_context_window_usage_visible,
                   is_related_content_visible, is_token_usage_visible,
                   is_current_user_message_visible, is_tool_observation_visible,
                   is_execution_model_tool_request_visible, is_tool_call_visible
            FROM conversation_preferences WHERE singleton_id = 1
            """
        ).fetchone()
    assert row == ("modifier_enter", 1, 0, 1, 1, 1, 0, 1)


def test_conversation_preferences_are_account_isolated_and_strictly_validated():
    app = create_app()
    alice = TestClient(app)
    bob = TestClient(app)
    _sign_up(alice, "alice")
    _sign_up(bob, "bob")

    alice_preferences = {
        **DEFAULT_PREFERENCES,
        "is_related_content_visible": False,
    }
    assert alice.put(
        "/api/account-settings/conversation-preferences",
        json=alice_preferences,
    ).status_code == 200
    assert bob.get(
        "/api/account-settings/conversation-preferences"
    ).json() == DEFAULT_PREFERENCES

    invalid = {
        **DEFAULT_PREFERENCES,
        "composer_submit_shortcut": "space",
    }
    response = alice.put(
        "/api/account-settings/conversation-preferences",
        json=invalid,
    )
    assert response.status_code == 422
    assert alice.get(
        "/api/account-settings/conversation-preferences"
    ).json() == alice_preferences

    unauthenticated = TestClient(app)
    assert unauthenticated.get(
        "/api/account-settings/conversation-preferences"
    ).status_code == 401
