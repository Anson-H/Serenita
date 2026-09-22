"""Separate append-only metadata and delivery histories for both SAG entity indexes."""
from backend.app.storage.memory.index_database import _table, _text, _ref, _hash
from backend.app.storage.schema import ColumnGroup as G, ForeignKey, CheckConstraint, Index


def _index_tables(binding_table, status_table, index_kind):
    return (
        _table(binding_table, ('binding_id',), (
            _text('entity_id', G.REFERENCE),
            *((_text('event_id', G.REFERENCE),) if index_kind == 'entity_role' else ()),
            *((_text('name_id', G.REFERENCE, nullable=True),) if index_kind == 'entity_name' else ()),
            _text('space_id', G.REFERENCE),
            _text('vector_id'),
            _text('text_hash'),
            _text('commit_id', G.AUDIT),
        ),
            refs=(_ref('entity_id', 'entities'), _ref('space_id', 'vector_spaces'),
                *((_ref('event_id', 'events'),) if index_kind == 'entity_role' else ()),
                *((ForeignKey(('entity_id', 'name_id'), 'entity_names', ('entity_id', 'name_id')), ) if index_kind == 'entity_name' else ())),
            checks=(_hash('text_hash'),),
            indexes=(Index(f'{binding_table}_identity', ('vector_id',), unique=True),
                Index(f'{binding_table}_target', ('account_id', 'member_id', 'entity_id', 'space_id')))),
        _table(status_table, ('binding_id', 'status_id'), (
            _text('previous_status_id', G.REFERENCE, nullable=True),
            _text('vector_hash', nullable=True),
            _text('state', G.STATE),
            _text('error_code', G.STATE, nullable=True),
            _text('error_message', G.STATE, nullable=True),
            _text('commit_id', G.AUDIT),
        ),
            refs=(_ref('binding_id', binding_table),
                ForeignKey(('binding_id', 'previous_status_id'), status_table, ('binding_id', 'status_id'))),
            checks=(_hash('vector_hash', nullable=True), CheckConstraint("state IN ('pending','confirmed','failed')"),
                CheckConstraint("(state='confirmed')=(vector_hash IS NOT NULL)"),
                CheckConstraint("(state='failed' AND error_code IS NOT NULL AND error_message IS NOT NULL) OR "
                    "(state<>'failed' AND error_code IS NULL AND error_message IS NULL)")),
            indexes=(Index(f'{status_table}_initial', ('binding_id',), unique=True, where='previous_status_id IS NULL'),
                Index(f'{status_table}_successor', ('binding_id', 'previous_status_id'), unique=True, where='previous_status_id IS NOT NULL'))),
    )

# Both command kinds share validation; each has its own physical tables.
SEMANTIC_INDEX_TARGETS = {
    'entity_name': ('entity_vectors', 'entity_vector_statuses'),
    'entity_role': ('event_entity_vectors', 'event_entity_vector_statuses'),
}
SEMANTIC_INDEX_TABLES = tuple(
    table for kind, names in SEMANTIC_INDEX_TARGETS.items()
    for table in _index_tables(*names, kind)
)
SEMANTIC_INDEX_COLLECTIONS = {
    'semantic_vector_bindings': (tuple(names[0] for names in SEMANTIC_INDEX_TARGETS.values()), None, None),
    'semantic_vector_statuses': (tuple(names[1] for names in SEMANTIC_INDEX_TARGETS.values()), None, None),
}
