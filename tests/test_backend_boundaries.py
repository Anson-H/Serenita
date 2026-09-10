"""Behavior at the explicit backend component boundaries."""

from contextlib import contextmanager
import sqlite3
import pytest

from backend.app.core.favorite_errors import FavoriteSourceConflictError
from backend.app.repositories.favorite_repository import FavoriteRepository


@pytest.mark.parametrize(
    "message, expected",
    [
        (
            "UNIQUE constraint failed: favorites.source_session_id, favorites.source_id",
            FavoriteSourceConflictError,
        ),
        (
            "UNIQUE constraint failed: favorites.member_id, favorites.source_id",
            FavoriteSourceConflictError,
        ),
        ("UNIQUE constraint failed: favorites.favorite_id", sqlite3.IntegrityError),
        ("CHECK constraint failed: source_type", sqlite3.IntegrityError),
    ],
)
def test_favorite_storage_classifies_only_source_duplicates(
    monkeypatch, message, expected
):
    repository = FavoriteRepository()

    @contextmanager
    def failing_connection(_account):
        raise sqlite3.IntegrityError(message)
        yield

    monkeypatch.setattr(repository, "_connection", failing_connection)
    with pytest.raises(expected):
        repository.create("account", dict(favorite_id="favorite", member_id=None, source_type="report", source_session_id="", source_id="report", title="标题", content_snapshot="内容", tags="[]", created_at="2026-09-10", updated_at="2026-09-10"))


def test_two_application_roots_keep_account_report_config_and_authorization_isolated(
    tmp_path, monkeypatch
):
    import uuid
    from backend.app.main import create_app
    from backend.app.storage.paths import AppPaths, app_paths
    from backend.app.storage.crypto import (
        seal_secret,
        unseal_secret,
        ProviderSecretError,
    )
    from backend.app.core.errors import SerenitaError
    from tests.api_client import TestClient
    from member_support import report_payload

    first = create_app(paths=AppPaths(tmp_path / "first"))
    second = create_app(paths=AppPaths(tmp_path / "second"))
    identity = uuid.uuid4()
    clients = [TestClient(first), TestClient(second)]
    try:
        with monkeypatch.context() as fixed_identity:
            fixed_identity.setattr(uuid, "uuid4", lambda: identity)
            for client in clients:
                response = client.post(
                    "/api/auth/sign_up",
                    json={
                        "account": "same",
                        "account_name": "same",
                        "password": "secret",
                        "confirm_password": "secret",
                    },
                )
                assert response.status_code == 200, response.text
        assert not app_paths().auth_db.exists()
        a, b = first.state.services, second.state.services
        member = (
            clients[0]
            .post("/api/members", json={"member_name": "甲"})
            .json()["member_id"]
        )
        created = clients[0].post(
            f"/api/members/{member}/reports", json=report_payload()
        )
        assert created.status_code == 201, created.text
        report_id = created.json()["report_id"]
        assert a.plugin_service(str(identity), member, "medical_report").report_exists(
            member, report_id
        )
        with a.members.access_guard(str(identity), member):
            with pytest.raises(SerenitaError):
                with b.members.access_guard(str(identity), member):
                    pytest.fail("another root reused active authorization")
        assert clients[1].get(f"/api/members/{member}/reports").status_code == 403
        secret = seal_secret(
            str(identity), "deepseek", "isolated-test-secret", paths=a.paths
        )
        assert (
            unseal_secret(str(identity), "deepseek", secret, paths=a.paths)
            == "isolated-test-secret"
        )
        seal_secret(str(identity), "deepseek", "second-root-secret", paths=b.paths)
        with pytest.raises(ProviderSecretError):
            unseal_secret(str(identity), "deepseek", secret, paths=b.paths)
        assert a.conversations.task_state is not b.conversations.task_state
        assert (
            a.conversations.repository.notifications
            is a.conversations.task_state.notifications
        )
        assert a.web.repository.paths.root == a.paths.root
        assert a.favorites.conversations is a.conversations
        assert a.auth.current_user(
            clients[0].cookies.get("serenita_auth_session_token")
        ).account_id == str(identity)
        with pytest.raises(SerenitaError):
            b.auth.current_user(clients[0].cookies.get("serenita_auth_session_token"))
    finally:
        for client in clients:
            client.close()


def test_nested_lifecycle_guards_acquire_each_roots_lock(tmp_path):
    import threading
    from backend.app.storage.paths import AppPaths
    from backend.app.core.member_lifecycle import member_lifecycle_guard

    first, second = AppPaths(tmp_path / "first"), AppPaths(tmp_path / "second")
    for paths in (first, second):
        paths.auth_db.parent.mkdir(parents=True, exist_ok=True)
    entered, release, acquired = threading.Event(), threading.Event(), threading.Event()

    def owner():
        with member_lifecycle_guard(exclusive=True, paths=second):
            entered.set()
            release.wait(5)

    def waiter():
        with member_lifecycle_guard(paths=first):
            with member_lifecycle_guard(paths=second):
                acquired.set()

    owner_thread = threading.Thread(target=owner)
    waiter_thread = threading.Thread(target=waiter)
    owner_thread.start()
    assert entered.wait(2)
    waiter_thread.start()
    try:
        assert not acquired.wait(0.1)
    finally:
        release.set()
        owner_thread.join(2)
        waiter_thread.join(2)
    assert acquired.is_set()


def test_probe_cancellation_is_scoped_and_stale_completion_cannot_remove_replacement(
    tmp_path,
):
    from backend.app.core.model_probe_tasks import probes_for_paths
    from backend.app.storage.paths import AppPaths

    first = probes_for_paths(AppPaths(tmp_path / "first"))
    second = probes_for_paths(AppPaths(tmp_path / "second"))
    old = first.begin("account", "model")
    other = second.begin("account", "model")
    replacement = first.begin("account", "model")
    assert old.is_cancelled and not other.is_cancelled
    first.finish("account", "model", old)
    probes_for_paths(AppPaths(tmp_path / "first")).cancel("account", "model")
    assert replacement.is_cancelled and not other.is_cancelled
    first.finish("account", "model", replacement)
    second.finish("account", "model", other)


@pytest.mark.parametrize("keep_other_item", [False, True])
def test_catalog_fact_failure_rolls_back_dictionary_analysis_and_cleanup(
    tmp_path, monkeypatch, keep_other_item
):
    import hashlib
    from member_support import account_id, member_id
    from backend.app.repositories.report_repository import ReportRepository
    from backend.app.repositories.report_transaction import ReportTransaction

    account, member = account_id("catalog"), member_id("catalog")
    repository = ReportRepository(account)
    source = repository.paths.report_attachment_path(
        account, "transaction-source", "txt"
    )
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("transaction evidence", encoding="utf-8")
    repository.register_source_file(
        member,
        resource_id="transaction-source",
        relative_path=str(source.relative_to(repository.paths.account_root(account))),
        mime_type="text/plain",
        size_bytes=source.stat().st_size,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        source_kind="unknown",
    )
    items = [
        {
            "item_id": "sodium",
            "item_name_zh": "血钠",
            "aliases": ["Na"],
            "category_name": "电解质",
            "result_text": "140 mmol/L",
            "reference_text": "137–147 mmol/L",
            "flag_text": "正常",
        }
    ]
    if keep_other_item:
        items.append(
            {
                **items[0],
                "item_id": "potassium",
                "item_name_zh": "血钾",
                "aliases": ["K"],
            }
        )
    created = repository.create_report_from_parsed(
        member,
        parsed_report={
            "report_type": "检验报告",
            "report_name": "电解质",
            "report_time": "2026-08-17T10:00:00+08:00",
            "institution_name": None,
            "lab_test_results": items,
        },
        resource_ids=["transaction-source"],
    )
    report_id = created["report_id"]
    repository.save_report_analysis(member, report_id, "existing interpretation")
    before_report = repository.get_report_detail(member, report_id)
    before_catalog = repository.lab_dictionary()
    transactions = []
    original_check = repository.catalog.require_dictionary_revision
    original_reconcile = repository.facts.reconcile_dictionary_report_changes

    def observe_transaction(transaction, revision):
        assert isinstance(transaction, ReportTransaction)
        transactions.append(transaction)
        return original_check(transaction, revision)

    def fail_after_fact_changes(transaction, report_ids):
        assert transaction is transactions[-1]
        effects = original_reconcile(transaction, report_ids)
        assert (
            effects[
                "updated_report_count" if keep_other_item else "deleted_report_count"
            ]
            == 1
        )
        raise RuntimeError("injected after fact changes")

    monkeypatch.setattr(
        repository.catalog, "require_dictionary_revision", observe_transaction
    )
    monkeypatch.setattr(
        repository.facts, "reconcile_dictionary_report_changes", fail_after_fact_changes
    )
    with pytest.raises(RuntimeError, match="injected after fact changes"):
        repository.delete_lab_item(
            "sodium", expected_dictionary_revision=before_catalog["dictionary_revision"]
        )
    assert repository.lab_dictionary() == before_catalog
    assert repository.get_report_detail(member, report_id) == before_report
    assert repository.file_cleanup_count(member) == 0
    assert source.read_text() == "transaction evidence"


from member_support import accounts as accounts


def test_member_reference_detach_failure_rolls_back_every_attached_database(
    accounts, monkeypatch
):
    from member_support import account_id, create_member, report_payload
    from backend.app.repositories.conversation_repository import ConversationRepository
    from backend.app.storage.private_references import PrivateReferenceStore
    from backend.app.storage.paths import app_paths
    from backend.app.storage.sqlite import connect

    owner = accounts[0]
    account = account_id("owner")
    member = create_member(owner, "transaction member")
    report = owner.post(f"/api/members/{member}/reports", json=report_payload()).json()
    favorite = owner.post(
        "/api/favorites",
        json={
            "source_type": "report",
            "member_id": member,
            "source_id": report["report_id"],
        },
    )
    assert favorite.status_code == 200, favorite.text
    conversations = ConversationRepository()
    session = conversations.ensure_session(account, member_id=member)
    original_detach = PrivateReferenceStore.detach
    detached = []

    def failing_detach(store, connection, alias, member_id):
        original_detach(store, connection, alias, member_id)
        detached.append(store.source)
        if store.source == "favorite":
            raise sqlite3.OperationalError("injected private reference failure")

    monkeypatch.setattr(PrivateReferenceStore, "detach", failing_detach)
    response = owner.delete(f"/api/members/{member}")
    assert response.status_code == 409, response.text
    assert detached == ["conversation", "favorite"]
    assert owner.get(f"/api/members/{member}").status_code == 200
    assert (
        owner.get(f"/api/members/{member}/reports/{report['report_id']}").status_code
        == 200
    )
    assert conversations.session_row(account, session)["member_id"] == member
    with connect(app_paths().favorites_db(account)) as connection:
        row = connection.execute(
            "SELECT member_id FROM favorites WHERE source_id = ?",
            (report["report_id"],),
        ).fetchone()
    assert row["member_id"] == member
