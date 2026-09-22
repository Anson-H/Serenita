"""Construct event/entity associations from resolved, evidenced identities."""
from types import SimpleNamespace
from zleap.sag.modules.extract.parser import ResultParser

def entity_associations(event_id, entities, identities):
    """Run the copied SAG association code with the host's evidenced identities."""
    def cache_key(entity_data):
        return (entity_data['type'], entity_data['name'])

    def resolve_entity(entity_data, entity_types):
        identity = identities.get(cache_key(entity_data))
        return SimpleNamespace(id=identity, name=entity_data['name']) if identity is not None else None

    parser = ResultParser(resolve_entity=resolve_entity, cache_key=cache_key)
    event = SimpleNamespace(id=event_id, extra_data={'raw_entities': {'entities': entities}})
    parser.process_entity_associations([event], [])
    return [{'event_id': row.event_id, 'entity_id': row.entity_id, 'description': row.description}
            for row in event.event_associations]

