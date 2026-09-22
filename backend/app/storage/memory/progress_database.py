"""Latest processing state per attempt and step; timestamps come from its commit."""
from backend.app.storage.schema import Column, ColumnGroup as G, Table, ForeignKey, CheckConstraint, Index


def text(name, group=G.DATA, *, nullable=False, json_kind=None):
    return Column(name, 'TEXT', group, nullable=nullable, json_kind=json_kind)


PROGRESS_TABLE = Table(name='processing_steps', columns=(
    text('attempt_id', G.PRIMARY_KEY), text('progress_id', G.PRIMARY_KEY),
    text('account_id', G.SCOPE), text('member_id', G.SCOPE),
    text('step_id'), text('parent_step_id', nullable=True),
    text('details_json', json_kind='object'),
    text('status', G.STATE),
    text('error_code', G.STATE, nullable=True), text('error_message', G.STATE, nullable=True),
    text('commit_id', G.AUDIT),
), primary_key=('attempt_id', 'progress_id'), foreign_keys=(
    ForeignKey(('commit_id', 'account_id', 'member_id'), 'commits', ('commit_id', 'account_id', 'member_id')),
    ForeignKey(('attempt_id', 'account_id', 'member_id'), 'processing_attempts', ('attempt_id', 'account_id', 'member_id')),
), checks=(CheckConstraint("status IN ('running','retrying','completed','failed','skipped')"),),
    indexes=(Index('processing_step_attempt', ('attempt_id', 'step_id'), unique=True,
        expressions=("COALESCE(parent_step_id, '')",)),))
