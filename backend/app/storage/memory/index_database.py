"""One append-only SQLite declaration for SAG metadata; vectors live in LanceDB."""
from backend.app.storage.schema import CheckConstraint, Column, ColumnGroup as G, ForeignKey, Index, Table, UniqueConstraint


def _text(name, group=G.DATA, *, nullable=False):
    return Column(name, "TEXT", group, nullable=nullable)


def _ref(column, table, target=None):
    return ForeignKey((column, "account_id", "member_id"), table, (target or column, "account_id", "member_id"))


def _table(name, keys, fields, *, refs=(), checks=(), indexes=(), scoped_unique=True):
    return Table(name=name, columns=(*(_text(key, G.PRIMARY_KEY) for key in keys), _text("account_id", G.SCOPE), _text("member_id", G.SCOPE),
        *fields), primary_key=keys,
        foreign_keys=(_ref("commit_id", "commits"), *refs),
        unique_constraints=(UniqueConstraint((*keys, "account_id", "member_id")),) if scoped_unique else (),
        checks=checks, indexes=indexes, append_only=True)


def _hash(name, *, nullable=False):
    rule = f"length({name}) = 64 AND {name} NOT GLOB '*[^0-9a-f]*'"
    return CheckConstraint(f"{name} IS NULL OR ({rule})" if nullable else rule)


MEMORY_INDEX_TABLES = (
    _table("entities", ("entity_id",), (
        _text("event_id", G.REFERENCE),
        _text("entity_type"),
        _text("canonical_name"),
        _text("formal_resource_type", nullable=True),
        _text("formal_resource_id", nullable=True),
        _text("commit_id", G.AUDIT),
    ),
        refs=(_ref("event_id", "events", "event_id"),),
        checks=(CheckConstraint("(formal_resource_type IS NULL) = (formal_resource_id IS NULL)"),)),
    _table("entity_names", ("entity_id", "name_id"), (
        _text("event_id", G.REFERENCE),
        _text("name"),
        _text("commit_id", G.AUDIT),
    ),
        refs=(_ref("entity_id", "entities"), _ref("event_id", "events", "event_id"))),
    _table("event_entities", ("event_id", "entity_id"), (
        _text("description"),
        _text("commit_id", G.AUDIT),
    ),
        refs=(_ref("event_id", "events"), _ref("entity_id", "entities")),
        indexes=(Index("event_entity_reverse", ("account_id", "member_id", "entity_id", "event_id")),), scoped_unique=False),
    _table("vector_spaces", ("space_id",), (
        _text("model_id"),
        _text("provider_id"),
        _text("remote_model_id"),
        _text("model_signature"),
        Column("dimensions", "INTEGER", G.DATA),

        _text("protocol"),
        _text("commit_id", G.AUDIT),
    ),
        checks=(_hash("model_signature"), CheckConstraint("dimensions > 0 AND dimensions <= 65536"), )),
    _table("event_vectors", ("binding_id",), (
        _text("event_id", G.REFERENCE),
        _text("space_id", G.REFERENCE),
        _text("vector_id"),
        _text("commit_id", G.AUDIT),
    ),
        refs=(_ref("event_id", "events"), _ref("space_id", "vector_spaces")),
        indexes=(Index("event_vectors_identity", ("vector_id",), unique=True), Index("event_vectors_event_space", ("account_id", "member_id", "event_id", "space_id")))),
    _table("vector_requests", ("attempt_id",), (
        _text("event_id", G.REFERENCE),
        _text("operation_id"),
        _text("requested_model_id", nullable=True),
        Column("requested_dimensions", "INTEGER", G.DATA, nullable=True),
        _text("commit_id", G.AUDIT),
    ),
        refs=(_ref("attempt_id", "processing_attempts"), _ref("event_id", "events")),
        checks=(CheckConstraint("requested_dimensions IS NULL OR (requested_dimensions > 0 AND requested_dimensions <= 65536)"),)),
    _table("event_vector_statuses", ("binding_id", "status_id"), (
        _text("previous_status_id", G.REFERENCE, nullable=True),
        _text("vector_hash", nullable=True),
        _text("state", G.STATE),
        _text("error_code", G.STATE, nullable=True),
        _text("error_message", G.STATE, nullable=True),
        _text("commit_id", G.AUDIT),
    ),
        refs=(_ref("binding_id", "event_vectors"), ForeignKey(("binding_id", "previous_status_id"), "event_vector_statuses", ("binding_id", "status_id"))),
        checks=(_hash("vector_hash", nullable=True), CheckConstraint("state IN ('pending','confirmed','failed')"),
                CheckConstraint("(state = 'confirmed') = (vector_hash IS NOT NULL)"),
                CheckConstraint("(state = 'failed' AND error_code IS NOT NULL AND error_message IS NOT NULL) OR (state <> 'failed' AND error_code IS NULL AND error_message IS NULL)")),
        indexes=(Index("event_vector_statuses_initial", ("binding_id",), unique=True, where="previous_status_id IS NULL"),
                 Index("event_vector_statuses_successor", ("binding_id", "previous_status_id"), unique=True, where="previous_status_id IS NOT NULL"))),
)

MEMORY_INDEX_COLLECTIONS = {
    "entities": ("entities", "entity", "entity_id"),
    "entity_names": ("entity_names", "entity_name", "name_id"),
    "event_entities": ("event_entities", None, None),
    "vector_spaces": ("vector_spaces", "vector_space", "space_id"),
    "vector_bindings": ("event_vectors", "vector_binding", "binding_id"),
    "vector_request_parameters": ("vector_requests", None, None),
    "vector_statuses": ("event_vector_statuses", "vector_status", "status_id"),
}
