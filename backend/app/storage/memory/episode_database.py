"""Canonical append-only episode table definitions."""
from backend.app.storage.schema import Column, ColumnGroup as G, Table, ForeignKey, UniqueConstraint, CheckConstraint, Index


def text(name, group=G.DATA, *, nullable=False, json_kind=None):
    return Column(name, "TEXT", group, nullable=nullable, json_kind=json_kind)


def integer(name, group=G.DATA, *, nullable=False):
    return Column(name, "INTEGER", group, nullable=nullable)


def ref(column, table, target=None):
    return ForeignKey((column, "account_id", "member_id"), table, (target or column, "account_id", "member_id"))


def table(name, keys, columns, *, refs=(), checks=(), indexes=()):
    key_columns = tuple(integer(key, G.PRIMARY_KEY) if key == "version" else text(key, G.PRIMARY_KEY) for key in keys)
    return Table(name=name, columns=(*key_columns, text("account_id", G.SCOPE), text("member_id", G.SCOPE),
        *columns), primary_key=keys,
        foreign_keys=(ref("commit_id", "commits"), *refs),
        unique_constraints=(UniqueConstraint((*keys, "account_id", "member_id")),), checks=checks, indexes=indexes, append_only=True)


EPISODE_TABLES = (
    table("episodes", ("episode_id",), (
        text("scope"),
        text("commit_id", G.AUDIT),
    )),
    table("episode_revisions", ("episode_id", "version"), (
        text("trigger_event_id", G.REFERENCE),
        text("summary"),
        text("state"),
        text("reason"),
        text("commit_id", G.AUDIT),
    ), refs=(ref("episode_id", "episodes"), ref("trigger_event_id", "events", "event_id")),
        checks=(CheckConstraint("version > 0"),),
        indexes=(Index("episode_revision_trigger", ("trigger_event_id",), unique=True),
                 Index("episode_revision_sequence", ("account_id", "member_id", "episode_id", "version")),)),
    table("episode_revision_inputs", ("episode_id", "version"), (
        text("attempt_id", G.REFERENCE),
        text("request_entry_id", G.REFERENCE),
        text("result_entry_id", G.REFERENCE),
        text("fixed_input_json", json_kind="object"),
        text("draft_scope", nullable=True),
        text("commit_id", G.AUDIT),
    ), refs=(ForeignKey(("episode_id", "version", "account_id", "member_id"), "episode_revisions",
        ("episode_id", "version", "account_id", "member_id")),
        ref("attempt_id", "processing_attempts"),
        ForeignKey(("attempt_id", "request_entry_id"), "execution_entries", ("attempt_id", "entry_id")),
        ForeignKey(("attempt_id", "result_entry_id"), "execution_entries", ("attempt_id", "entry_id"))),
        checks=(CheckConstraint("version > 0"),)),
    table("event_episode", ("event_id",), (
        text("episode_id", G.REFERENCE),
        text("reason"),
        text("commit_id", G.AUDIT),
    ), refs=(ref("event_id", "events"), ref("episode_id", "episodes")),
        indexes=(Index("membership_episode", ("account_id", "member_id", "episode_id", "event_id", "commit_id")),)),

)

EPISODE_COLLECTIONS = {
    "episodes": ("episodes", "episode", "episode_id"),
    "episode_revisions": ("episode_revisions", "episode_revision", "version"),
    "episode_revision_inputs": ("episode_revision_inputs", None, "episode_id"),
    "episode_memberships": ("event_episode", "episode_membership", "event_id"),
}
