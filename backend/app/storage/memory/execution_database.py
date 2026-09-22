"""The sole declaration of append-only execution records."""
from backend.app.storage.schema import Column, ColumnGroup as G, Table, ForeignKey, UniqueConstraint, CheckConstraint, Index


def text(name, group=G.DATA, *, json_kind=None, nullable=False):
    return Column(name, 'TEXT', group, json_kind=json_kind, nullable=nullable)


def number(name):
    return Column(name, 'INTEGER', G.DATA)


def scope():
    return (text('account_id', G.SCOPE), text('member_id', G.SCOPE))


def refs():
    return (ForeignKey(('commit_id', 'account_id', 'member_id'), 'commits', ('commit_id', 'account_id', 'member_id')),
            ForeignKey(('attempt_id', 'account_id', 'member_id'), 'processing_attempts', ('attempt_id', 'account_id', 'member_id')))


EXECUTION_TABLES = (
    Table(name='execution_entries', columns=(
        text('attempt_id', G.PRIMARY_KEY),
        text('entry_id', G.PRIMARY_KEY),
        *scope(),
        number('entry_sequence'),
        text('entry_kind'),
        text('payload_json', json_kind='object'),
        text('dependencies_json', json_kind='array'),
        text('commit_id', G.AUDIT),
    ),
        primary_key=('attempt_id', 'entry_id'), foreign_keys=refs(),
        unique_constraints=(UniqueConstraint(('attempt_id', 'entry_sequence')),),
        checks=(CheckConstraint('entry_sequence > 0'),
            CheckConstraint("entry_kind IN ('model_request','model_result')")), append_only=True),
)
EXECUTION_COLLECTIONS = {
    'execution_entries': ('execution_entries', 'memory_execution_entry', 'entry_id'),
}
