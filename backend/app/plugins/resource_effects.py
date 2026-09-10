"""Describe completed resource operations for conversation presentation."""


def resource_effects(reference, change=None):
    effects = {"affected_resource_refs" if change == "deleted" else "resource_refs": [reference]}
    entity = {"entity_type": reference["resource_type"], "entity_id": reference["resource_id"]}
    if change == "created":
        effects["created_entities"] = [entity]
    elif change:
        effects["changed_entities"] = [{**entity, "change": change}]
    return effects
