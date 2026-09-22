"""Record initial public preferences inside their creation transaction."""
from uuid import NAMESPACE_URL, uuid5

from backend.app.repositories.business_change_repository import record_change
from backend.app.repositories.business_operation_repository import begin_operation, finish_operation


_PREFERENCE_TABLES = {
    "member_preference": "member_preferences",
    "conversation_preference": "conversation_preferences",
    "notification_preference": "account_preferences",
}


def record_initial_preference(connection, actor, resource_type, *, schema_alias="main"):
    table = _PREFERENCE_TABLES[resource_type]
    operation_id = str(uuid5(NAMESPACE_URL, f"serenita:initial-preference:{actor}:{resource_type}"))
    replay = begin_operation(connection, actor, operation_id,
                             {"domain": resource_type, "action": "initialize"}, schema_alias=schema_alias)
    if replay is not None:
        return
    # begin_operation has already validated and quoted the database alias.
    row = connection.execute(f'SELECT * FROM "{schema_alias}".{table} WHERE singleton_id=1').fetchone()
    if row is None:
        raise ValueError("初始偏好必须与其真实内容共同保存。")
    fields = {f"/{key}": row[key] for key in row.keys() if key not in {"singleton_id", "notifications_updated_at"}}
    record_change(connection, actor_account_id=actor, operation_id=operation_id, scope_kind="account", member_id=None,
                  resource_type=resource_type, resource_id="1", before=None, after=fields,
                  context={"preference_kind": resource_type}, origin_kind="manual", schema_alias=schema_alias)
    finish_operation(connection, actor, operation_id, {"initialized": True}, schema_alias=schema_alias)
