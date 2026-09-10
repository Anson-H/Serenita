"""Successful health record changes remain navigable through conversation effects."""

from uuid import uuid4
import pytest
from member_support import accounts, account_id, create_member, grant
from tests.test_medications import drug, plan_values
from tests.test_body_metrics import measurement
from backend.app.application.conversations.service import ConversationService
from backend.app.core.errors import SerenitaError
from backend.app.plugins import PluginRuntimeContext, build_available_tools


@pytest.mark.parametrize("kind", ["medical_log", "medication_plan", "medication_batch", "body_record"])
def test_changed_health_resources_resolve_live_states_and_keep_deleted_references(accounts, kind):
    owner, _, _ = accounts
    member = create_member(owner)
    actor = account_id("owner")
    context = PluginRuntimeContext(account_id=actor, member_id=member, event_recorder=lambda _: None)
    tools = {tool.name: tool for tool in build_available_tools(runtime_context=context)}
    request_id = str(uuid4())
    if kind == "medical_log":
        stem, id_field = "log", "medical_log_id"
        payload = {"recorded_on": "2026-09-10", "title": "睡眠随记", "content": "今天睡得不太好。"}
        changes = {"content": "今天睡得不太好，午休后好些了。"}
    elif kind == "body_record":
        stem, id_field = "body_record", "record_id"
        payload = {"record": measurement(), "request_id": request_id}
        changes = {"changes": {"notes": "已确认测量"}}
    else:
        medication = drug(owner, member)
        stem, id_field = kind, f"{kind}_id"
        payload = {"request_id": request_id, "medication_id": medication["medication_id"]}
        payload.update(plan_values() if kind == "medication_plan" else {"quantity": "12"})
        changes = {"notes": "已确认安排"}
    created = tools[f"create_{stem}"].run(payload)
    reference = created.effects["resource_refs"][0]
    resource_id = reference["resource_id"]
    assert reference["resource_type"] == kind
    assert reference["member_id"] == member
    assert reference["name"]
    assert created.effects["created_entities"] == [{"entity_type": kind, "entity_id": resource_id}]
    if kind == "medication_batch":
        assert reference["medication_id"] == medication["medication_id"]
    service = ConversationService()
    records = [{"kind": "tool", "result": {"effects": created.effects}}]
    def states(viewer=actor):
        return service.queries._conversation_resource_states(viewer, member, records)
    assert states()[0]["availability"] == "available"
    updated = tools[f"update_{stem}"].run({id_field: resource_id, **changes})
    assert updated.effects["changed_entities"] == [{"entity_type": kind, "entity_id": resource_id, "change": "modified"}]
    records.append({"kind": "tool", "result": {"effects": updated.effects}})
    assert len(states()) == 1
    assert states()[0]["current_updated_at"] == updated.effects["resource_refs"][0]["updated_at"]
    grants = grant(owner, member, "reader", "read")
    assert states(account_id("reader"))[0]["availability"] == "available"
    owner.delete(f"/api/account-settings/member-grants/{member}/{grants[0]['account_id']}")
    assert states(account_id("reader"))[0]["availability"] == "forbidden"
    deleted = tools[f"delete_{stem}"].run({id_field: resource_id})
    assert deleted.effects["affected_resource_refs"][0]["resource_id"] == resource_id
    assert "resource_refs" not in deleted.effects
    records.append({"kind": "tool", "result": {"effects": deleted.effects}})
    assert states()[0]["availability"] == "deleted"
    # A failed change produces no completed operation to append to the conversation.
    with pytest.raises(SerenitaError):
        tools[f"update_{stem}"].run({id_field: resource_id, **changes})
