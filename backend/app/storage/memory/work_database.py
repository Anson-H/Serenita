"""Attempt-local deltas and checkpoints; never a durable formal memory copy."""
from backend.app.storage.schema import CheckConstraint, Column, ColumnGroup as G, Database, Table


MEMORY_WORK_DATABASE_SCHEMA = Database(name='work.db', tables=(
    Table(name='work_values', columns=(
        Column('key', 'TEXT', G.PRIMARY_KEY, nullable=False),
        Column('value_json', 'TEXT', G.DATA, nullable=False),
    ), primary_key=('key',), checks=(CheckConstraint('json_valid(value_json)'),)),
))
