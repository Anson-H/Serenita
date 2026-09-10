from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
import sqlite3

import pytest

from member_support import accounts, account_id, create_member, grant
from backend.app.application.medical_history_service import MedicalHistoryService
from backend.app.core.errors import SerenitaError
from backend.app.plugins.medical_history.registry import build_tools
from backend.app.plugins.runtime_context import PluginRuntimeContext
from backend.app.schemas.medical_history import MEDICAL_HISTORY_FIELDS
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect


def test_history_partial_updates_clear_and_explicit_unknown(accounts):
    owner, _, _ = accounts
    member = create_member(owner)
    url = f"/api/members/{member}/medical-history"
    empty = owner.get(url).json()
    assert len(empty["history"]) == 8
    assert all(value == {"text": None, "updated_at": None} for value in empty["history"].values())
    values = {name: f"{label}：不详" for name, (label, _) in MEDICAL_HISTORY_FIELDS.items()}
    saved = owner.patch(url, json=values)
    assert saved.status_code == 200, saved.text
    history = saved.json()["history"]
    assert len({item["updated_at"] for item in history.values()}) == 1
    assert owner.patch(url, json=values).json()["history"] == history
    changed = owner.patch(url, json={"allergy_history": "否认药物过敏史", "surgical_trauma_history": "无", "transfusion_vaccination_history": "不详"}).json()["history"]
    assert changed["past_medical_history"] == history["past_medical_history"]
    assert changed["surgical_trauma_history"]["text"] == "无"
    selected = owner.get(url, params=[("fields", "allergy_history"), ("fields", "transfusion_vaccination_history")]).json()["history"]
    assert set(selected) == {"allergy_history", "transfusion_vaccination_history"}
    cleared = owner.patch(url, json={"allergy_history": None, "surgical_trauma_history": "", "transfusion_vaccination_history": " \n "}).json()["history"]
    for name in ("allergy_history", "surgical_trauma_history", "transfusion_vaccination_history"):
        assert cleared[name]["text"] is None
        assert cleared[name]["updated_at"] is not None
    for invalid in ({}, {"allergy_history": "新值", "unknown": "禁止"}, {"allergy_history": 5}):
        assert owner.patch(url, json=invalid).status_code == 422
        assert owner.get(url).json()["history"] == cleared
    assert owner.get(url, params=[("fields", "allergy_history"), ("fields", "allergy_history")]).status_code == 400


def test_tools_and_page_share_history_with_live_permissions(accounts):
    owner, reader, editor = accounts
    member = create_member(owner)
    other = create_member(owner)
    grant(owner, member, "reader", "read")
    grant(owner, member, "editor", "edit")
    def tools(actor):
        return build_tools(runtime_context=PluginRuntimeContext(account_id=account_id(actor), member_id=member, event_recorder=lambda _: None))
    read, update = tools("editor")
    assert read.model_exposure == update.model_exposure == "direct"
    update.run({"family_history": "父亲患高血压", "allergy_history": "无"})
    assert owner.get(f"/api/members/{member}/medical-history").json()["history"]["family_history"]["text"] == "父亲患高血压"
    fresh_read, _ = tools("reader")
    assert fresh_read.run({"fields": ["allergy_history"]}).output["history"]["allergy_history"]["text"] == "无"
    assert owner.get(f"/api/members/{other}/medical-history").json()["history"]["allergy_history"]["text"] is None
    assert reader.patch(f"/api/members/{member}/medical-history", json={"allergy_history": "x"}).status_code == 403
    _, reader_update = tools("reader")
    with pytest.raises(SerenitaError): reader_update.run({"allergy_history": "x"})
    assert owner.delete(f"/api/account-settings/member-grants/{member}/{account_id('editor')}").status_code == 200
    with pytest.raises(SerenitaError): update.run({"allergy_history": "x"})
    with pytest.raises(PermissionError):
        update.bind_runtime_arguments({}, context=SimpleNamespace(account_id=account_id("editor"), member_id=other), observations=[])
    assert build_tools(runtime_context=PluginRuntimeContext(account_id=account_id("owner"), event_recorder=lambda _: None)) == []
    assert owner.delete(f"/api/members/{member}").status_code == 200
    with connect(app_paths().members_db(account_id("owner"))) as db:
        assert db.execute("SELECT 1 FROM medical_history WHERE member_id = ?", (member,)).fetchone() is None
    with pytest.raises(SerenitaError): fresh_read.run({})


def test_history_storage_failure_rolls_back_whole_update(accounts):
    owner, _, _ = accounts
    member = create_member(owner)
    service = MedicalHistoryService()
    actor = account_id("owner")
    before = service.update(actor, member, {"allergy_history": "原值", "family_history": "原值"})
    with connect(app_paths().members_db(actor)) as db:
        db.execute("CREATE TRIGGER fail_history BEFORE UPDATE ON medical_history BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        service.update(actor, member, {"allergy_history": "更新", "family_history": "更新"})
    assert service.read(actor, member) == before


def test_history_concurrent_updates_and_revoke_wait_for_write(accounts, monkeypatch):
    owner, _, _ = accounts
    member = create_member(owner)
    grant(owner, member, "editor", "edit")
    service = MedicalHistoryService()
    actor = account_id("editor")
    owner_id = account_id("owner")
    entered, release = Event(), Event()
    original = service.repository.update
    def held(access, values):
        entered.set()
        assert release.wait(5)
        return original(access, values)
    monkeypatch.setattr(service.repository, "update", held)
    with ThreadPoolExecutor(2) as pool:
        write = pool.submit(service.update, actor, member, {"allergy_history": "无"})
        assert entered.wait(5)
        revoke = pool.submit(service.members.revoke, owner_id, member, actor)
        assert not revoke.done()
        release.set()
        assert write.result(timeout=5)["history"]["allergy_history"]["text"] == "无"
        revoke.result(timeout=5)
    with pytest.raises(SerenitaError): service.update(actor, member, {"allergy_history": "新值"})
    monkeypatch.setattr(service.repository, "update", original)
    owner_id = account_id("owner")
    with ThreadPoolExecutor(2) as pool:
        results = [pool.submit(service.update, owner_id, member, values) for values in ({"family_history": "父亲高血压"}, {"surgical_trauma_history": "无"})]
        for result in results: result.result(timeout=5)
    service.update(owner_id, member, {"allergy_history": "明确修正"})
    history = service.read(owner_id, member)["history"]
    assert history["allergy_history"]["text"] == "明确修正"
    assert history["family_history"]["text"] == "父亲高血压"
    assert history["surgical_trauma_history"]["text"] == "无"
