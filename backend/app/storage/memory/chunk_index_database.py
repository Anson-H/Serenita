"""Source-fragment references and delivery history; source text stays outside SQLite memory."""
from backend.app.storage.memory.index_database import _table, _text, _ref, _hash
from backend.app.storage.schema import Column, ColumnGroup as G, ForeignKey, CheckConstraint, Index


CHUNK_INDEX_TABLES = (
    _table('source_chunks', ('binding_id',), (
        _text('chunk_id', G.REFERENCE), _text('event_id', G.REFERENCE), _text('space_id', G.REFERENCE),
        _text('source_database', G.REFERENCE), _text('change_id', G.REFERENCE),
        Column('field_path', 'TEXT', G.REFERENCE, nullable=False, non_blank=False),
        _text('vector_id'), Column('character_start', 'INTEGER', G.DATA, nullable=False),
        Column('character_end', 'INTEGER', G.DATA, nullable=False), Column('rank', 'INTEGER', G.DATA, nullable=False),
        _text('text_hash'), _text('commit_id', G.AUDIT),
    ), refs=(_ref('event_id', 'events'), _ref('space_id', 'vector_spaces')),
        checks=(_hash('text_hash'), CheckConstraint('character_start >= 0 AND character_end > character_start'),
            CheckConstraint('rank >= 1')),
        indexes=(Index('source_chunks_identity', ('vector_id',), unique=True),
            Index('source_chunks_event', ('account_id', 'member_id', 'event_id', 'space_id')))),
    _table('source_chunk_statuses', ('binding_id', 'status_id'), (
        _text('previous_status_id', G.REFERENCE, nullable=True), _text('vector_hash', nullable=True),
        _text('state', G.STATE), _text('error_code', G.STATE, nullable=True), _text('error_message', G.STATE, nullable=True),
        _text('commit_id', G.AUDIT),
    ), refs=(_ref('binding_id', 'source_chunks'),
        ForeignKey(('binding_id', 'previous_status_id'), 'source_chunk_statuses', ('binding_id', 'status_id'))),
        checks=(_hash('vector_hash', nullable=True), CheckConstraint("state IN ('pending','confirmed','failed')"),
            CheckConstraint("(state='confirmed')=(vector_hash IS NOT NULL)"),
            CheckConstraint("(state='failed' AND error_code IS NOT NULL AND error_message IS NOT NULL) OR "
                "(state<>'failed' AND error_code IS NULL AND error_message IS NULL)")),
        indexes=(Index('source_chunk_statuses_initial', ('binding_id',), unique=True, where='previous_status_id IS NULL'),
            Index('source_chunk_statuses_successor', ('binding_id', 'previous_status_id'), unique=True, where='previous_status_id IS NOT NULL'))),
)

CHUNK_INDEX_COLLECTIONS = {
    'chunk_vector_bindings': ('source_chunks', None, None),
    'chunk_vector_statuses': ('source_chunk_statuses', None, None),
}
