"""Validate Event–Entity roles on append; read their immutable stored text."""
from backend.app.domain.memory.entity_associations import entity_associations
from backend.app.domain.memory.vectors import fail


def validate_event_entity(repo, db, access, event, entity, description, mentions):
    """Check a SAG association against the extraction used in this append."""
    if mentions is None:
        return
    mentions = [mention for mention in mentions if mention['type'] == entity['entity_type']
        and mention['entity_id'] == entity['entity_id']]
    names = {mention['name'] for mention in mentions}
    associations = entity_associations(event['event_id'], mentions,
        {(entity['entity_type'], name): entity['entity_id'] for name in names})
    if not associations or associations[0]['description'] != description:
        fail('MEMORY_EVENT_ENTITY_DESCRIPTION_UNPROVEN', '实体作用说明必须完整采用该事件实际提取的说明。')


def read_entity_association(repo, db, access, entity, description):
    """Read an immutable association visible at the requested record cutoff."""
    repo._require(db, access, 'event', description['event_id'])
    linked = db.execute(
        'SELECT l.event_id,l.entity_id,l.description FROM event_entities l JOIN commits c USING(commit_id) '
        'WHERE l.event_id=? AND l.entity_id=? AND l.account_id=? AND l.member_id=? AND c.sequence<=?',
        (description['event_id'], entity['entity_id'], access.account_id, access.member_id,
         repo._cutoff(db, access))).fetchone()
    if linked is None:
        fail('MEMORY_SEMANTIC_TEXT_UNPROVEN', '实体作用向量须引用已保存的事件与实体关联。')
    return dict(linked)


def entity_role_text(repo, db, access, entity, description):
    return read_entity_association(repo, db, access, entity, description)['description']
