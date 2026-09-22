"""Immutable recovery audit survives disposal of attempt-local work."""
from backend.app.storage.schema import CheckConstraint, Column, ColumnGroup as G, ForeignKey, Index, Table, UniqueConstraint


RECOVERY_RECORDS_TABLE = Table(name='recovery_records', columns=(
        Column('recovery_id', 'TEXT', G.PRIMARY_KEY, nullable=False),
        Column('account_id', 'TEXT', G.SCOPE, nullable=False),
        Column('member_id', 'TEXT', G.SCOPE, nullable=False),
        Column('attempt_id', 'TEXT', G.REFERENCE, nullable=False),
        Column('operation_id', 'TEXT', G.DATA, nullable=False),
        Column('kind', 'TEXT', G.DATA, nullable=False),
        Column('checkpoint_json', 'TEXT', G.DATA, nullable=False),
        Column('retry_epoch', 'INTEGER', G.DATA, nullable=False),
        Column('recorded_at', 'DATETIME', G.AUDIT, nullable=False),
    ), primary_key=('recovery_id',), unique_constraints=(UniqueConstraint(('account_id', 'member_id', 'operation_id')),),
       foreign_keys=(ForeignKey(('attempt_id', 'account_id', 'member_id'), 'processing_attempts',
                                ('attempt_id', 'account_id', 'member_id')),),
       checks=(CheckConstraint("kind IN ('auto','explicit')"), CheckConstraint('json_valid(checkpoint_json)'),
               CheckConstraint("typeof(retry_epoch)='integer' AND retry_epoch>=0")),
       indexes=(Index('recovery_attempt_time', ('attempt_id', 'recorded_at', 'recovery_id')),), append_only=True)
