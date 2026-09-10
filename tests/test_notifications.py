from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import asyncio
import time
import pytest
from member_support import accounts, account_id, create_member, grant, import_report
from test_medications import plan, drug, url
from backend.app.application.services import ApplicationServices
from backend.app.core.errors import SerenitaError
from backend.app.repositories.notification_repository import timestamp
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect
from backend.app.application.medication_notifications import (
    MedicationNotificationProducer,
    medication_validity_key,
    expired_content,
)
from backend.app.application.notification_scheduler import ScheduledCall


from backend.app.application.conversations.service import ConversationService
from backend.app.application.conversations.notifications import completion_event
from tests.model_support import ConversationModelCatalog


def answer(actor, *, services, member=None, session=None, run=True):
    chat = ConversationService(model_catalog=ConversationModelCatalog(), services=services)
    queued = chat.send_message(actor, session, "test question", "model_1", "default", [], member_id=member)
    if run:
        chat.start_turn_job(actor, queued["session_id"], queued["stream_id"])
        chat.wait_for_turn_job(actor, queued["session_id"], queued["stream_id"], timeout=10)
        assert chat.repository.turn_row(actor, queued["session_id"], queued["turn_id"])["status"] == "completed"
    return chat, queued


def reminder(owner, *, services=None, member=None):
    services = services or ApplicationServices()
    member = member or create_member(owner)
    saved = plan(owner, member)
    actor = account_id("owner")
    services.notifications.set_preferences(actor, True)
    producer = MedicationNotificationProducer(services.notifications)
    producer.publish(actor, member, saved, datetime.now(timezone.utc))
    item = services.notifications.list(actor)["items"][0]
    return services, member, saved, item


def test_answer_notification_is_private_and_supports_no_member(accounts):
    owner, reader, _ = accounts
    member = create_member(owner)
    grant(owner, member, "reader", "read")
    services = ApplicationServices()
    svc = services.notifications
    actor, recipient = account_id("owner"), account_id("reader")
    assert svc.preferences(actor)["notifications_enabled"] is False
    for user in (actor, recipient):
        svc.set_preferences(user, True)
    for bound in (member, None):
        chat, queued = answer(actor, services=services, member=bound)
        svc.dispatch(actor)
        item = svc.list(actor)["items"][0]
        assert item["notification_type"] == "answer_completed"
        assert item["title"] == "回答已生成"
        assert item["message"] == chat.repository.session_row(actor, queued["session_id"])["title"]
        assert item["target"] == {"member_id": None, "resource_type": "conversation", "resource_id": queued["session_id"]}
        assert item["actions"] == ["read"]
        assert svc.list(recipient)["items"] == []
        svc.act(actor, item["notification_id"], "read")
    assert svc.summary(actor)["pending_count"] == 0
    assert len(svc.list(actor, status="read")["items"]) == 2
    assert not app_paths().medications_db(recipient).exists()
    answer(recipient, services=services, member=member)
    svc.dispatch(recipient)
    assert len(svc.list(recipient)["items"]) == 1
    assert svc.list(actor)["items"] == []


def test_close_preserves_received_and_skips_closed_period(accounts):
    owner, *_ = accounts
    services, member, saved, item = reminder(owner)
    service = services.notifications
    actor = account_id("owner")
    opened = service.preferences(actor)["notifications_enabled_since"]
    assert service.set_preferences(actor, True)["notifications_enabled_since"] == opened
    service.set_preferences(actor, False)
    assert service.list(actor)["items"][0]["notification_id"] == item["notification_id"]
    assert service.summary(actor)["pending_count"] == 1
    producer = MedicationNotificationProducer(service)
    closed_at = datetime.now(timezone.utc)
    assert producer.publish(actor, member, saved, closed_at) == "skipped"
    assert service.act(actor, item["notification_id"], "read")["status"] == "read"
    service.set_preferences(actor, True)
    assert producer.publish(actor, member, saved, closed_at) == "skipped"
    assert service.list(actor)["items"] == []
    assert len(service.list(actor, status="read")["items"]) == 1


@pytest.mark.parametrize("notification_type", ["medication_due", "medication_expired", "answer_completed"])
def test_type_switches_gate_delivery_and_reopening_without_changing_others(accounts, notification_type):
    owner, *_ = accounts
    services, member, saved, received = reminder(owner)
    svc = services.notifications
    actor = account_id("owner")
    producer = MedicationNotificationProducer(svc)
    if notification_type == "answer_completed":
        _, queued = answer(actor, services=services)
        content = completion_event(actor, queued["session_id"], queued["turn_id"], timestamp())["content"]
    elif notification_type == "medication_expired":
        batch = services.medications.save(actor, member, "batch", {
            "quantity": "1", "expires_on": (datetime.now().date() - timedelta(days=1)).isoformat(),
        }, request_id=str(uuid4()), medication_id=saved["medication_id"])
        content = expired_content(member, batch, datetime.now(timezone.utc))
    else:
        content = producer.content(member, saved, datetime.now(timezone.utc))
    key = f"{notification_type}_enabled"
    svc.set_preferences(actor, **{key: False})
    closed = svc.preferences(actor)
    assert closed["notifications_enabled"] is True
    for other in ("medication_due", "medication_expired", "answer_completed"):
        assert closed[f"{other}_enabled"] is (other != notification_type)
    assert svc.deliver(actor, str(uuid4()), content) == "skipped"
    assert svc.list(actor)["items"][0]["notification_id"] == received["notification_id"]
    svc.act(actor, received["notification_id"], "read")
    svc.set_preferences(actor, False)
    assert all(not svc.preferences(actor)[f"{name}_enabled"] for name in ("medication_due", "medication_expired", "answer_completed"))
    opened = svc.set_preferences(actor, **{key: True})
    assert svc.set_preferences(actor, **{key: True}) == opened
    assert svc.deliver(actor, str(uuid4()), content) == "skipped"
    content["occurred_at"] = content["available_at"] = timestamp()
    assert svc.deliver(actor, str(uuid4()), content) == "delivered"
    assert svc.list(actor)["items"][0]["notification_type"] == notification_type
    assert len(svc.list(actor, status="read")["items"]) == 1


def test_notification_preferences_api_is_partial_strict_and_account_scoped(accounts):
    owner, reader, _ = accounts
    path = "/api/account-settings/notifications"
    initial = owner.get(path).json()
    assert initial["notifications_enabled"] is False
    assert all(not initial[f"{name}_enabled"] for name in ("medication_due", "medication_expired", "answer_completed"))
    response = owner.put(path, json={"medication_due_enabled": True, "answer_completed_enabled": True})
    assert response.status_code == 200
    assert response.json()["medication_expired_enabled"] is False
    assert response.json()["notifications_enabled"] is True
    assert reader.get(path).json()["medication_due_enabled"] is False
    assert ApplicationServices().notifications.preferences(account_id("owner")) == response.json()
    for invalid in ({}, {"medication_expired_enabled": None}, {"medication_expired_enabled": 1}, {"medication_expired_enabled": "false"}, {"unknown_enabled": True}, {"notifications_enabled": False, "medication_due_enabled": True}):
        assert owner.put(path, json=invalid).status_code in (400, 422)
    assert owner.get(path).json() == response.json()


def test_concurrent_type_settings_do_not_overwrite_other_switches(accounts):
    svc = ApplicationServices().notifications
    actor = account_id("owner")
    keys = ["medication_due_enabled", "medication_expired_enabled", "answer_completed_enabled"]
    for enabled in (True, False):
        with ThreadPoolExecutor(3) as pool:
            list(pool.map(lambda key: svc.set_preferences(actor, **{key: enabled}), keys))
        assert all(svc.preferences(actor)[key] is enabled for key in keys)
        assert svc.preferences(actor)["notifications_enabled"] is enabled


def test_total_and_child_notification_switches_are_linked(accounts):
    owner, *_ = accounts
    path = "/api/account-settings/notifications"
    keys = ["medication_due_enabled", "medication_expired_enabled", "answer_completed_enabled"]
    def save(changes, expected):
        response = owner.put(path, json=changes)
        assert response.status_code == 200
        value = response.json()
        assert [value[key] for key in keys] == expected
        assert value["notifications_enabled"] is any(expected)
        assert owner.get(path).json() == value
        return value
    save({"notifications_enabled": True}, [True, True, True])
    save({"medication_due_enabled": False}, [False, True, True])
    save({"notifications_enabled": False}, [False, False, False])
    for index, key in enumerate(keys):
        expected = [False, False, False]
        expected[index] = True
        opened = save({key: True}, expected)
        assert save({key: True}, expected) == opened
        save({key: False}, [False, False, False])
    save({"notifications_enabled": True}, [True, True, True])
    save({"notifications_enabled": False}, [False, False, False])


def test_answer_deduplicates_and_new_turns_create_new_notifications(accounts):
    services = ApplicationServices()
    svc = services.notifications
    actor = account_id("owner")
    svc.set_preferences(actor, True)
    chat, queued = answer(actor, services=services)
    svc.dispatch(actor)
    first = svc.list(actor)["items"][0]
    svc.act(actor, first["notification_id"], "read")
    turn = chat.repository.turn_row(actor, queued["session_id"], queued["turn_id"])
    chat.repository.update_turn_completed(actor, queued["session_id"], queued["turn_id"], queued["final_assistant_message_id"], turn["updated_at"], notification_event=completion_event(actor, queued["session_id"], queued["turn_id"], turn["updated_at"]))
    svc.dispatch(actor)
    assert svc.list(actor)["items"] == []
    assert len(svc.list(actor, status="read")["items"]) == 1
    regenerated = chat.regenerate_message(actor, queued["session_id"], queued["final_assistant_message_id"], "model_1", "default")
    chat.start_turn_job(actor, queued["session_id"], regenerated["stream_id"])
    chat.wait_for_turn_job(actor, queued["session_id"], regenerated["stream_id"], timeout=10)
    svc.dispatch(actor)
    assert len(svc.list(actor)["items"]) == 1
    answer(actor, services=services, session=queued["session_id"])
    svc.dispatch(actor)
    assert len(svc.list(actor)["items"]) == 2
    chat.delete_conversation(actor, queued["session_id"])
    assert svc.list(actor)["items"] == []
    assert svc.list(actor, status="read")["items"] == []


def test_answer_outbox_is_atomic_and_delivery_recovers(accounts, monkeypatch):
    services = ApplicationServices()
    svc = services.notifications
    actor = account_id("owner")
    svc.set_preferences(actor, True)
    chat, queued = answer(actor, services=services, run=False)
    from backend.app.repositories.notification_repository import NotificationRepository
    original = NotificationRepository.enqueue
    def fail(*args, **kwargs):
        raise RuntimeError("injected enqueue failure")
    monkeypatch.setattr(NotificationRepository, "enqueue", fail)
    with pytest.raises(RuntimeError):
        chat.repository.update_turn_completed(actor, queued["session_id"], queued["turn_id"], queued["final_assistant_message_id"], notification_event=completion_event(actor, queued["session_id"], queued["turn_id"], timestamp()))
    assert chat.repository.turn_row(actor, queued["session_id"], queued["turn_id"])["status"] == "queued"
    assert svc.repository.pending(actor) == []
    monkeypatch.setattr(NotificationRepository, "enqueue", original)
    chat.start_turn_job(actor, queued["session_id"], queued["stream_id"])
    chat.wait_for_turn_job(actor, queued["session_id"], queued["stream_id"], timeout=10)
    finish = svc.repository.finish_delivery
    failed = []
    def once(owner, row, status, error=None):
        if status == "delivered" and not failed:
            failed.append(True)
            raise RuntimeError("after recipient commit")
        return finish(owner, row, status, error)
    monkeypatch.setattr(svc.repository, "finish_delivery", once)
    svc.dispatch(actor)
    svc.dispatch(actor, datetime.now(timezone.utc) + timedelta(seconds=10))
    assert len(svc.list(actor)["items"]) == 1
    assert svc.repository.pending(actor, datetime.now(timezone.utc) + timedelta(days=1)) == []


def test_revoke_and_delete_hide_both_lists_and_counts(accounts):
    owner, reader, _ = accounts
    services, member, saved, item = reminder(owner)
    actor = account_id("owner")
    recipient = account_id("reader")
    grant(owner, member, "reader", "read")
    services.notifications.set_preferences(recipient, True)
    MedicationNotificationProducer(services.notifications).publish(
        recipient, member, saved, datetime.now(timezone.utc)
    )
    read_item = services.notifications.list(recipient)["items"][0]
    services.notifications.act(recipient, read_item["notification_id"], "read")
    services.member_service.revoke(actor, member, recipient)
    assert services.notifications.list(recipient, status="read")["items"] == []
    assert services.notifications.summary(recipient)["pending_count"] == 0
    with pytest.raises(SerenitaError):
        services.notifications.act(recipient, read_item["notification_id"], "read")
    owner.delete(url(member, "medication-plans", saved["medication_plan_id"]))
    assert services.notifications.list(actor)["items"] == []


def test_concurrent_read_actions_and_current_medication_identity(accounts):
    owner, *_ = accounts
    services, member, saved, item = reminder(owner)
    svc = services.notifications
    actor = account_id("owner")
    owner.patch(
        f'/api/medication-catalog/{saved["medication_id"]}', json={"generic_name": "当前药名"}
    )
    current = svc.list(actor)["items"][0]
    assert "当前药名" in current["message"]
    assert current["actions"] == ["read"]
    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(
                lambda _: svc.act(actor, item["notification_id"], "read"), range(2)
            )
        )
    assert all(result["status"] == "read" for result in results)
    assert svc.summary(actor)["pending_count"] == 0 and not svc.list(actor)["items"]
    changed = drug(owner, member)
    owner.patch(
        url(member, "medication-plans", saved["medication_plan_id"]),
        json={"medication_id": changed["medication_id"]},
    )
    with pytest.raises(SerenitaError):
        svc.act(actor, item["notification_id"], "read")


@pytest.mark.parametrize("with_member", [False, True])
def test_notifications_are_application_owned(accounts, monkeypatch, with_member):
    from backend.app.plugins.registry import build_available_tools
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    from backend.app.plugins import registry

    owner, *_ = accounts
    services = ApplicationServices()
    actor = account_id("owner")
    member = create_member(owner) if with_member else None
    context = PluginRuntimeContext(
        account_id=actor,
        member_id=member,
        event_recorder=lambda _: None,
        service_factory=lambda name: services.plugin_service(actor, member, name),
    )
    names = {tool.name for tool in build_available_tools(runtime_context=context)}
    assert names.isdisjoint({
        "read_notifications", "update_notification_preferences", "update_notification",
    })

    # Notification delivery and scheduling remain available with no agent plugins.
    monkeypatch.setattr(registry, "discover_plugin_registries", lambda: [])
    services = ApplicationServices()
    assert set(services.notifications.types) == {
        "answer_completed", "medication_due", "medication_expired",
    }
    scheduler = services.notification_scheduler
    assert len(scheduler.producers) == 1
    services.notifications.set_preferences(actor, True)
    chat, queued = answer(actor, services=services, member=member)
    services.notifications.dispatch(actor)
    items = owner.get("/api/notifications").json()["items"]
    assert len(items) == 1
    assert items[0]["resource_id"] == queued["session_id"]
    response = owner.post(
        f"/api/notifications/{items[0]['notification_id']}/actions",
        json={"action": "read"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "read"



def test_notification_pagination_skips_invalid_rows_and_cursor_is_scoped(accounts):
    owner, *_ = accounts
    services, member, saved, item = reminder(owner)
    svc = services.notifications
    actor = account_id("owner")
    with connect(app_paths().notifications_db(actor)) as db:
        for n in range(510):
            row = dict(db.execute("SELECT * FROM notifications LIMIT 1").fetchone())
            row["notification_id"] = f"z{n:05}"
            row["resource_id"] = "deleted"
            svc.repository.insert(db, "notifications", row)
    first = svc.list(actor, limit=1)
    assert first["next_cursor"]
    second = svc.list(actor, limit=1, cursor=first["next_cursor"])
    assert second["items"][0]["notification_id"] == item["notification_id"]
    with pytest.raises(SerenitaError):
        svc.list(account_id("reader"), cursor=first["next_cursor"])


def test_live_scheduler_does_not_depend_on_recovery(accounts):
    owner, *_ = accounts
    services, member, saved, item = reminder(owner)
    svc = services.notifications
    actor = account_id("owner")
    scheduler = services.notification_scheduler
    due = datetime.now(timezone.utc) + timedelta(seconds=0.15)
    producer = MedicationNotificationProducer(svc)
    fired = []

    class Producer:
        def jobs(self, at):
            return [
                ScheduledCall(
                    due.timestamp(),
                    lambda: (
                        (
                            producer.publish(actor, member, saved, due),
                            fired.append(time.monotonic()),
                        )
                        and None
                    ),
                )
            ]

    scheduler.producers = [Producer()]

    async def verify():
        task = asyncio.create_task(scheduler.live())
        try:
            deadline = time.monotonic() + 3
            while not fired and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            assert fired
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(verify())
    assert len(svc.list(actor)["items"]) == 2


def test_checkpoint_failure_keeps_same_interval_and_no_duplicate(accounts, monkeypatch):
    owner, *_ = accounts
    services, member, saved, item = reminder(owner)
    svc = services.notifications
    actor = account_id("owner")
    producer = MedicationNotificationProducer(svc)
    at = datetime.now(timezone.utc)
    original = svc.repository.complete_checkpoint

    def fail(*args):
        raise RuntimeError("checkpoint failure")

    monkeypatch.setattr(svc.repository, "complete_checkpoint", fail)
    with pytest.raises(RuntimeError):
        producer.recover_actor(actor, at)
    row = svc.repository.checkpoint(
        actor,
        producer.task_name,
        svc.preferences(actor)["notifications_enabled_since"],
        timestamp(at + timedelta(hours=1)),
    )
    assert row["scan_until"] == timestamp(at)
    monkeypatch.setattr(svc.repository, "complete_checkpoint", original)
    producer.recover(at + timedelta(hours=1))
    assert len(svc.list(actor)["items"]) == 1


def test_report_save_and_manual_edit_do_not_notify(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    services = ApplicationServices()
    actor = account_id("owner")
    services.notifications.set_preferences(actor, True)
    report_id = import_report("owner", member)["report_id"]
    report = services.report(actor, member)
    report.write_report_analysis(member, report_id=report_id, analysis_content="saved analysis", session_id="s")
    report.update_report_field(member, report_id, field="analysis_content", value="manual edit")
    assert services.notifications.repository.pending(actor) == []
    assert services.notifications.list(actor)["items"] == []


@pytest.mark.parametrize("failure", ["error", "empty", "cancel"])
def test_failed_empty_and_cancelled_answers_do_not_notify(accounts, failure):
    from backend.app.agent_runtime.model_types import ModelStreamChunk
    from tests.model_support import BlockingConversationModelCatalog

    class FailedCatalog(ConversationModelCatalog):
        def stream_prepared_chat_for_account(self, **kwargs):
            if failure == "error":
                raise RuntimeError("injected generation failure")
            yield ModelStreamChunk(stop_reason="end_turn")

    services = ApplicationServices()
    actor = account_id("owner")
    services.notifications.set_preferences(actor, True)
    catalog = BlockingConversationModelCatalog() if failure == "cancel" else FailedCatalog()
    chat = ConversationService(model_catalog=catalog, services=services)
    queued = chat.send_message(actor, None, "test failure", "model_1", "default", [], member_id=None)
    chat.start_turn_job(actor, queued["session_id"], queued["stream_id"])
    if failure == "cancel":
        try:
            assert catalog.first_chunk_persisted.wait(timeout=5)
            chat.cancel_turn(actor, queued["session_id"], queued["turn_id"])
        finally:
            catalog.release.set()
    chat.wait_for_turn_job(actor, queued["session_id"], queued["stream_id"], timeout=10)
    assert chat.repository.turn_row(actor, queued["session_id"], queued["turn_id"])["status"] != "completed"
    assert services.notifications.repository.pending(actor) == []
    assert services.notifications.list(actor)["items"] == []


def test_offline_revoke_regrant_and_pause_resume_do_not_revive(accounts):
    owner, reader, _ = accounts
    services, member, plan_value, item = reminder(owner)
    svc = services.notifications
    actor = account_id("owner")
    recipient = account_id("reader")
    grant(owner, member, "reader", "read")
    svc.set_preferences(recipient, True)
    producer = MedicationNotificationProducer(svc)
    producer.publish(recipient, member, plan_value, datetime.now(timezone.utc))
    services.member_service.revoke(actor, member, recipient)
    grant(owner, member, "reader", "read")
    assert svc.list(recipient)["items"] == []
    owner.patch(
        url(member, "medication-plans", plan_value["medication_plan_id"]),
        json={"usage_status": "paused", "schedule": None},
    )
    owner.patch(
        url(member, "medication-plans", plan_value["medication_plan_id"]),
        json={
            "usage_status": plan_value["usage_status"],
            "schedule": plan_value["schedule"],
        },
    )
    assert svc.list(actor)["items"] == []
    assert svc.repository.get(actor, item["notification_id"])["status"] == "cancelled"


def test_scheduler_rearms_earlier_and_idle_checks_do_not_query_business(
    accounts, monkeypatch
):
    services = ApplicationServices()
    scheduler = services.notification_scheduler
    runtime = services.notifications.runtime
    at = time.time()
    due = [at + 100]
    calls = []

    class Producer:
        def jobs(self, now):
            calls.append(now)
            return [ScheduledCall(due[0], lambda: None)]

    scheduler.producers = [Producer()]
    scheduler.step()
    assert scheduler.heap[0][0] == at + 100
    due[0] = at + 10
    runtime.changed(reschedule=True)
    scheduler.step()
    assert scheduler.heap[0][0] == at + 10 and len(calls) == 2
    monkeypatch.setattr(
        scheduler.repository, "accounts", lambda: pytest.fail("idle scan")
    )
    scheduler.step()
    assert len(calls) == 2
    scheduler.clock_offset -= 5
    scheduler.step()
    assert len(calls) == 3


def test_count_returns_unknown_for_unverifiable_type(accounts):
    owner, *_ = accounts
    services, _, _, item = reminder(owner)
    actor = account_id("owner")
    services.notifications.types.clear()
    summary = services.notifications.summary(actor)
    assert summary["pending_count"] is None and summary["errors"]
    assert services.notifications.list(actor)["items"] == []


@pytest.mark.parametrize(
    "exit_at", ["before_commit", "after_commit", "after_recipient_commit"]
)
def test_process_exit_recovers_atomic_answer_and_delivery(accounts, exit_at):
    import subprocess
    import sys
    services = ApplicationServices()
    svc = services.notifications
    actor = account_id("owner")
    svc.set_preferences(actor, True)
    chat, queued = answer(actor, services=services, run=False)
    script = """
import os,sys
from backend.app.application.services import ApplicationServices
from backend.app.application.conversations.service import ConversationService
from backend.app.repositories.notification_repository import NotificationRepository
from tests.model_support import ConversationModelCatalog
actor,session,stream,stage=sys.argv[1:]
services=ApplicationServices()
chat=ConversationService(model_catalog=ConversationModelCatalog(), services=services)
if stage=='before_commit':
    NotificationRepository.enqueue=lambda *a,**k:os._exit(23)
chat.start_turn_job(actor,session,stream)
chat.wait_for_turn_job(actor,session,stream,timeout=10)
if stage=='after_recipient_commit':
    services.notifications.repository.finish_delivery=lambda *a,**k:os._exit(23)
    services.notifications.dispatch(actor)
os._exit(23)
"""
    result = subprocess.run([sys.executable, "-c", script, actor, queued["session_id"], queued["stream_id"], exit_at], timeout=15)
    assert result.returncode == 23
    turn = chat.repository.turn_row(actor, queued["session_id"], queued["turn_id"])
    svc.dispatch(actor)
    if exit_at == "before_commit":
        assert turn["status"] != "completed" and svc.list(actor)["items"] == []
    else:
        assert turn["status"] == "completed" and len(svc.list(actor)["items"]) == 1
        assert not svc.repository.pending(actor)


def test_account_scoped_type_receives_authenticated_scope_without_member(accounts):
    from backend.app.application.notification_service import NotificationService
    from backend.app.application.notification_types import NotificationType

    services = ApplicationServices()
    actor = account_id("owner")

    def load(scope, ids):
        assert (
            scope.account_id == actor
            and scope.actor_account_id == actor
            and scope.member_id is None
        )
        return {"session": {}}

    adapter = NotificationType(
        "answer_completed",
        "conversation",
        load,
        lambda row, resource: {"details": []},
        requires_member=False,
    )
    svc = NotificationService(services.members, types={"answer_completed": adapter})
    svc.set_preferences(actor, True)
    content = {
        "member_id": None,
        "resource_type": "conversation",
        "resource_id": "session",
        "notification_type": "answer_completed",
        "occurred_at": timestamp(),
        "available_at": timestamp(),
        "title": "账号事项",
        "message": "账号通知",
        "validity_key": "turn",
        "event_revision": 1,
    }
    svc.deliver(actor, "account-event", content)
    assert svc.list(actor)["items"][0]["target"] == {
        "member_id": None,
        "resource_type": "conversation",
        "resource_id": "session",
    }
    assert not app_paths().medications_db(actor).exists()
