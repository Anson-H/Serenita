"""The sole SQL declaration for immutable Event edges."""
from backend.app.schemas.memory.relations import RELATION_TYPES
from backend.app.storage.schema import CheckConstraint, Column, ColumnGroup as G, ForeignKey, Index, Table, UniqueConstraint


def text(name, group=G.DATA, *, nullable=False, json_kind=None):
    return Column(name, "TEXT", group, nullable=nullable, json_kind=json_kind)


def ref(column, table, target=None):
    return ForeignKey((column, "account_id", "member_id"), table, (target or column, "account_id", "member_id"))


def choice(name, values):
    return CheckConstraint(f"{name} IN ({','.join(repr(value) for value in values)})")


def table(name, keys, fields, *, references=(), unique=(), indexes=(), checks=()):
    return Table(name=name, columns=(
        *(text(key, G.PRIMARY_KEY) for key in keys), text("account_id", G.SCOPE), text("member_id", G.SCOPE),
        *fields), primary_key=keys,
        foreign_keys=(ref("commit_id", "commits"), *references),
        unique_constraints=(UniqueConstraint((*keys, "account_id", "member_id")), *unique),
        indexes=indexes, checks=checks, append_only=True)


MEMORY_RELATION_TABLES = (
    table("event_relations", ("relation_id",), (
        text("from_event_id", G.REFERENCE),
        text("to_event_id", G.REFERENCE),
        text("relation_type"),
        text("reason"),
        text("commit_id", G.AUDIT),
    ),
        references=(ref("from_event_id", "events", "event_id"), ref("to_event_id", "events", "event_id")),
        indexes=(Index("relation_pair", ("account_id", "member_id"), unique=True, expressions=("min(from_event_id, to_event_id)", "max(from_event_id, to_event_id)")),
                 Index("relation_from", ("account_id", "member_id", "from_event_id", "to_event_id")),
                 Index("relation_to", ("account_id", "member_id", "to_event_id", "from_event_id"))),
        checks=(CheckConstraint("from_event_id <> to_event_id"), choice("relation_type", RELATION_TYPES))),
)

MEMORY_RELATION_COLLECTIONS = {"event_relations": ("event_relations", "event_relation", "relation_id")}
