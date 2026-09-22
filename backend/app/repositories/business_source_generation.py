"""Read an object creation identity from its immutable business change ledger."""

def business_generation(connection, resource_type, resource_id, member_id, *, at_sequence=None):
    """Bind a journal change to its creation, and reject a deleted live generation.

    A historical delete still belongs to its preceding create. Current checks
    instead reject a last lifecycle action of delete even if an unjournaled
    same-id row appears. Missing creation evidence has no inferred generation.
    """
    if at_sequence is not None and (type(at_sequence) is not int or at_sequence < 1):
        raise ValueError("历史来源截点必须是正整数。")
    condition = "resource_type=? AND resource_id=? AND member_id IS ?"
    parameters = [resource_type, resource_id, member_id]
    if at_sequence is not None:
        condition += " AND change_sequence<=?"
        parameters.append(at_sequence)
    lifecycle = connection.execute(
        "SELECT change_id,operation_kind FROM business_changes WHERE " + condition +
        " AND operation_kind IN ('create','delete') ORDER BY change_sequence DESC LIMIT 1",
        parameters,
    ).fetchone()
    if lifecycle is None or (at_sequence is None and lifecycle["operation_kind"] == "delete"):
        return None
    if lifecycle["operation_kind"] == "create":
        return "change:" + lifecycle["change_id"]
    creation = connection.execute(
        "SELECT change_id FROM business_changes WHERE " + condition +
        " AND operation_kind='create' ORDER BY change_sequence DESC LIMIT 1", parameters,
    ).fetchone()
    return "change:" + creation["change_id"] if creation is not None else None
