"""Medication reminder deadlines and one-time batch expiration notifications."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import sqlite3
import threading
from uuid import uuid4

import pytest
from member_support import accounts, account_id, create_member, grant
from test_medications import drug, plan, plan_values, url
from backend.app.application.services import ApplicationServices
from backend.app.application import medication_notifications
from backend.app.application.medication_notifications import MedicationNotificationProducer, batch_expiration
from backend.app.repositories.notification_repository import timestamp
from backend.app.storage.sqlite import connect


def freeze(monkeypatch, at):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return at.astimezone(tz) if tz else at.astimezone().replace(tzinfo=None)
    monkeypatch.setattr(medication_notifications, "datetime", Clock)


def setup(owner):
    services = ApplicationServices()
    member, actor = create_member(owner), account_id("owner")
    medication = drug(owner, member)
    svc = services.notifications
    svc.set_preferences(actor, True)
    return services, svc, member, actor, medication


def batch(services, actor, member, medication, **changes):
    return services.medications.save(actor, member, "batch", {
        "quantity": "2", "expires_on": (datetime.now().date() - timedelta(days=1)).isoformat(), **changes,
    }, request_id=str(uuid4()), medication_id=medication["medication_id"])


def backdate(svc, actor, saved, at):
    lower = timestamp(at - timedelta(days=3))
    with connect(svc.paths.config_db(actor)) as db:
        db.execute("UPDATE account_preferences SET notifications_enabled_since=?,medication_due_enabled_since=?", (lower, lower))
    with connect(svc.paths.medications_db(actor)) as db:
        db.execute("UPDATE medication_plans SET created_at=?,updated_at=? WHERE medication_plan_id=?", (lower, lower, saved["medication_plan_id"]))
    return lower


@pytest.mark.parametrize("age,expected", [(599.999, "delivered"), (600, "skipped"), (601, "skipped"), (86400, "skipped"), (-1, "skipped")])
def test_delivery_enforces_ten_minute_window(accounts, monkeypatch, age, expected):
    owner, *_ = accounts
    services, svc, member, actor, medication = setup(owner)
    saved = plan(owner, member, medication)
    at = datetime.now(timezone.utc)
    backdate(svc, actor, saved, at)
    freeze(monkeypatch, at)
    producer = MedicationNotificationProducer(svc)
    assert producer.publish(actor, member, saved, at - timedelta(seconds=age)) == expected
    assert len(svc.list(actor)["items"]) == (expected == "delivered")


def test_recovery_only_recent_reminders_and_restart_deduplicates(accounts, monkeypatch):
    owner, *_ = accounts
    services, svc, member, actor, medication = setup(owner)
    at = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    times = sorted({(at-timedelta(minutes=n)).strftime("%H:%M") for n in (5, 10, 11)})
    saved = plan(owner, member, medication, plan_values(
        starts_at=(at-timedelta(days=4)).replace(hour=0, minute=0).isoformat(), timezone="UTC",
        schedule={"kind": "daily", "times": [{"time": value} for value in times]},
    ))
    backdate(svc, actor, saved, at)
    freeze(monkeypatch, at)
    producer = MedicationNotificationProducer(svc)
    complete = svc.repository.complete_checkpoint
    monkeypatch.setattr(svc.repository, "complete_checkpoint", lambda *args: (_ for _ in ()).throw(RuntimeError("interrupted")))
    with pytest.raises(RuntimeError):
        producer.recover_actor(actor, at)
    first = svc.list(actor)["items"]
    assert len(first) == 1
    assert first[0]["occurred_at"] == timestamp(at-timedelta(minutes=5))
    monkeypatch.setattr(svc.repository, "complete_checkpoint", complete)
    restarted = ApplicationServices().notifications
    MedicationNotificationProducer(restarted).recover_actor(actor, at)
    assert [row["notification_id"] for row in restarted.list(actor)["items"]] == [first[0]["notification_id"]]
    # Received notifications remain history; an old unfinished scan emits nothing new.
    freeze(monkeypatch, at+timedelta(hours=1))
    MedicationNotificationProducer(restarted).recover_actor(actor, at+timedelta(hours=1))
    assert len(restarted.list(actor)["items"]) == 1


def test_stale_scheduled_callback_cannot_deliver(accounts, monkeypatch):
    owner, *_ = accounts
    services, svc, member, actor, medication = setup(owner)
    at = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(hours=1)
    saved = plan(owner, member, medication, plan_values(
        starts_at=(at-timedelta(days=1)).replace(hour=0, minute=0).isoformat(), timezone="UTC",
        schedule={"kind": "daily", "times": [{"time": at.strftime("%H:%M")}]},
    ))
    producer = MedicationNotificationProducer(svc)
    job = producer.next_job(actor, member, saved, at-timedelta(seconds=1))
    freeze(monkeypatch, at+timedelta(minutes=10))
    assert job.callback() is not None
    assert svc.list(actor)["items"] == []


def test_expiration_once_per_batch_across_retries_restart_and_reopening(accounts):
    owner, *_ = accounts
    services, svc, member, actor, medication = setup(owner)
    first = batch(services, actor, member, medication)
    second = batch(services, actor, member, medication)
    batch(services, actor, member, medication, quantity="0")
    batch(services, actor, member, medication, expires_on=None)
    batch(services, actor, member, medication, expires_on=datetime.now().date().isoformat())
    producer = MedicationNotificationProducer(svc)
    at = datetime.now(timezone.utc)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda _: producer.publish_expired(actor, member, first, at), range(2)))
    producer.recover_actor(actor, datetime.now(timezone.utc))
    items = svc.list(actor)["items"]
    assert len(items) == 2
    assert {item["target"]["resource_id"] for item in items} == {first["medication_batch_id"], second["medication_batch_id"]}
    assert all(item["target"]["medication_id"] == medication["medication_id"] for item in items)
    assert all(item["title"] == "药品已过期" for item in items)
    for item in items:
        svc.act(actor, item["notification_id"], "read")
    svc.set_preferences(actor, False)
    svc.set_preferences(actor, True)
    restarted = ApplicationServices().notifications
    fresh = MedicationNotificationProducer(restarted)
    fresh.recover_actor(actor, datetime.now(timezone.utc))
    for job in fresh.jobs(datetime.now(timezone.utc)):
        job.callback()
    assert restarted.list(actor)["items"] == []
    assert len(restarted.list(actor, status="read")["items"]) == 2


def test_expiration_deadline_is_after_last_valid_day(accounts, monkeypatch):
    owner, *_ = accounts
    services, svc, member, actor, medication = setup(owner)
    saved = batch(services, actor, member, medication, expires_on=(datetime.now().date()+timedelta(days=1)).isoformat())
    expiration = batch_expiration(saved)
    assert expiration.astimezone().date().isoformat() > saved["expires_on"]
    assert expiration.astimezone().hour == 0
    producer = MedicationNotificationProducer(svc)
    freeze(monkeypatch, expiration-timedelta(seconds=1))
    producer.recover_actor(actor, expiration-timedelta(seconds=1))
    assert svc.list(actor)["items"] == []
    jobs = producer.jobs(expiration-timedelta(seconds=1))
    assert len(jobs) == 1 and jobs[0].at == expiration.timestamp()
    freeze(monkeypatch, expiration)
    jobs[0].callback()
    rows = svc.repository.rows(actor, at=expiration)
    assert len(rows) == 1 and rows[0]["notification_type"] == "medication_expired"


def test_expiration_switch_permissions_and_batch_changes(accounts):
    owner, reader, _ = accounts
    services, svc, member, actor, medication = setup(owner)
    recipient = account_id("reader")
    saved = batch(services, actor, member, medication)
    producer = MedicationNotificationProducer(svc)
    svc.set_preferences(actor, medication_expired_enabled=False)
    producer.recover_actor(actor, datetime.now(timezone.utc))
    assert svc.list(actor)["items"] == []
    svc.set_preferences(actor, medication_expired_enabled=True)
    grant(owner, member, "reader", "read")
    svc.set_preferences(recipient, medication_expired_enabled=True)
    producer.recover(datetime.now(timezone.utc))
    assert len(svc.list(actor)["items"]) == len(svc.list(recipient)["items"]) == 1
    services.members.revoke(actor, member, recipient)
    assert svc.list(recipient)["items"] == []
    services.medications.save(actor, member, "batch", {"expires_on": (datetime.now().date()+timedelta(days=30)).isoformat()}, object_id=saved["medication_batch_id"])
    assert svc.list(actor)["items"] == []
    services.medications.save(actor, member, "batch", {"expires_on": saved["expires_on"]}, object_id=saved["medication_batch_id"])
    producer.recover_actor(actor, datetime.now(timezone.utc))
    assert svc.list(actor)["items"] == []
    another = batch(services, actor, member, medication)
    producer.recover_actor(actor, datetime.now(timezone.utc))
    assert len(svc.list(actor)["items"]) == 1
    services.medications.delete(actor, member, "batch", another["medication_batch_id"])
    assert svc.list(actor)["items"] == []


def test_shared_notification_scan_finishes_before_waiting_grant_revocation(accounts, monkeypatch):
    from backend.app.core.errors import SerenitaError

    owner, _, _ = accounts
    services, svc, member, actor, medication = setup(owner)
    saved = plan(owner, member, medication)
    recipient = account_id("reader")
    grant(owner, member, "reader", "read")
    svc.set_preferences(recipient, True)
    at = datetime.now(timezone.utc)
    granted_at = at - timedelta(days=1)
    earlier = timestamp(at - timedelta(days=3))
    with connect(svc.paths.auth_db) as db:
        db.execute("UPDATE member_grants SET updated_at=? WHERE member_id=? AND account_id=?", (timestamp(granted_at), member, recipient))
    with connect(svc.paths.config_db(recipient)) as db:
        db.execute("UPDATE account_preferences SET notifications_enabled_since=?,medication_due_enabled_since=?", (earlier, earlier))
    with connect(svc.paths.medications_db(actor)) as db:
        db.execute("UPDATE medication_plans SET created_at=?,updated_at=? WHERE medication_plan_id=?", (earlier, earlier, saved["medication_plan_id"]))

    waiting, release = threading.Event(), threading.Event()
    failures = []

    def revoke_grant():
        try:
            with sqlite3.connect(svc.paths.auth_db, timeout=0) as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM member_grants WHERE member_id=? AND account_id=?", (member, recipient))
                # A failed zero-timeout commit retains the pending writer lock,
                # so another reader cannot start while the original guard lives.
                with pytest.raises(sqlite3.OperationalError, match="locked"):
                    db.commit()
                waiting.set()
                assert release.wait(10), "notification scan did not release its guard"
                db.commit()
        except BaseException as exc:
            failures.append(exc)
            waiting.set()

    original_guard = services.members.access_guard

    @contextmanager
    def guard(actor_id, member_id, *, write=False):
        worker = None
        try:
            with original_guard(actor_id, member_id, write=write) as access:
                if actor_id == recipient and member_id == member:
                    worker = threading.Thread(target=revoke_grant)
                    worker.start()
                    assert waiting.wait(3), "grant revocation did not reach commit"
                    assert failures == []
                yield access
        finally:
            if worker is not None:
                release.set()
                worker.join(3)
                assert not worker.is_alive()

    with monkeypatch.context() as patch:
        patch.setattr(services.members, "access_guard", guard)
        results = MedicationNotificationProducer(svc).plans(recipient, "medication_due")
    assert failures == []
    assert [(value[0], value[1]["medication_plan_id"], value[2]) for value in results] == [
        (member, saved["medication_plan_id"], granted_at)
    ]
    with pytest.raises(SerenitaError) as revoked:
        services.members.resolve(recipient, member)
    assert revoked.value.code == "MEMBER_ACCESS_UNAVAILABLE"


def test_pending_delivery_retry_expires_after_ten_minutes(accounts, monkeypatch):
    owner, *_ = accounts
    services, svc, member, actor, medication = setup(owner)
    saved = plan(owner, member, medication)
    due = datetime.now(timezone.utc)
    producer = MedicationNotificationProducer(svc)
    svc.repository.initialize(actor)
    with connect(svc.paths.notifications_db(actor)) as db:
        svc.repository.enqueue(db, 'retry-reminder', [actor], producer.content(member, saved, due), alias='main')
    actual = svc.deliver
    monkeypatch.setattr(svc, 'deliver', lambda *args: (_ for _ in ()).throw(RuntimeError('temporary failure')))
    svc.dispatch(actor)
    monkeypatch.setattr(svc, 'deliver', actual)
    freeze(monkeypatch, due+timedelta(minutes=10))
    svc.dispatch(actor, due+timedelta(minutes=10))
    assert svc.list(actor)['items'] == []
    with connect(svc.paths.notifications_db(actor)) as db:
        row = db.execute('SELECT status,attempt_count FROM notification_outbox WHERE event_id=?', ('retry-reminder',)).fetchone()
    assert tuple(row) == ('skipped', 1)


def test_new_notification_preferences_api_is_strict_and_account_scoped(accounts):
    owner, reader, _ = accounts
    path = '/api/account-settings/notifications'
    response = owner.put(path, json={'medication_expired_enabled': True})
    assert response.status_code == 200
    prefs = response.json()
    assert prefs['notifications_enabled'] is True
    assert prefs['medication_expired_enabled'] is True
    assert prefs['medication_due_enabled'] is False
    assert reader.get(path).json()['medication_expired_enabled'] is False
    assert owner.put(path, json={'unsupported_enabled': True}).status_code == 422
    assert owner.put(path, json={'medication_expired_enabled': None}).status_code == 400
    response = owner.put(path, json={'notifications_enabled': True})
    assert all(response.json()[key] for key in ('medication_expired_enabled','medication_due_enabled','answer_completed_enabled'))
