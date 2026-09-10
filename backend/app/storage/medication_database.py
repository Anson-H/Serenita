"""Single Python definition of the medication database."""
from typing import get_args
from backend.app.storage.schema import Column, ColumnGroup as G, Database, Table, ForeignKey, Index, CheckConstraint, UniqueConstraint
from backend.app.schemas.medication import MODELS, IDS, TABLES


def col(name, group=G.DATA, nullable=True, storage='TEXT', **rules):
    return Column(name, storage, group, nullable=nullable, **rules)


def object_checks(kind):
    if kind == 'medication':
        return (CheckConstraint("prescription_type IN ('prescription','nonprescription','unknown')"),)
    if kind == 'batch':
        return (CheckConstraint("length(quantity) BETWEEN 1 AND 120 AND quantity NOT GLOB '*[^0-9.]*' AND quantity GLOB '[0-9]*' AND quantity NOT LIKE '%.%.%' AND quantity NOT LIKE '%.'"),)
    return (
        CheckConstraint("start_precision IN ('date','minute')"),
        CheckConstraint("end_precision IS NULL OR end_precision IN ('date','minute')"),
        CheckConstraint("((ends_at IS NULL OR ends_at = 'long_term') AND end_precision IS NULL) OR (ends_at IS NOT NULL AND ends_at <> 'long_term' AND end_precision IS NOT NULL)"),
        CheckConstraint("usage_status IN ('taking','paused','stopped','completed','unknown')"),
        CheckConstraint("usage_status NOT IN ('paused','stopped','completed') OR schedule IS NULL"),
    )


def object_table(kind):
    model, key = MODELS[kind], IDS[kind]
    refs = [n for n in ('medication_id',) if n in model.model_fields]
    if kind == 'batch': refs = ['medication_id']
    states = [n for n in ('prescription_type', 'usage_status') if n in model.model_fields]
    data = [n for n in model.model_fields if n not in {*refs, *states}]
    fks = []
    if 'medication_id' in refs:
        fks.append(ForeignKey(('medication_id',), 'medications', ('medication_id',), on_delete='RESTRICT'))
    return Table(TABLES[kind], (
        col(key, G.PRIMARY_KEY, False),
        *((col('member_id', G.SCOPE, False),) if kind != 'medication' else ()),
        *(col(n, G.REFERENCE, False) for n in refs),
        *(col(n, nullable=type(None) in get_args(model.model_fields[n].annotation), non_blank=True if n in ('brand_name', 'ends_at', 'expires_on', 'leaflet_url') else None, json_kind='object' if n == 'schedule' else None) for n in data),
        *(col(n, G.STATE, False) for n in states), col('created_at', G.AUDIT, False), col('updated_at', G.AUDIT, False),
    ), (key,), foreign_keys=tuple(fks), checks=object_checks(kind), indexes=(Index(f'{TABLES[kind]}_catalog', ('created_at', key) if kind == 'medication' else ('member_id', 'created_at', key)),))


MEDICATION_DATABASE_SCHEMA = Database('medications.db', (
    # 药品管理：资料、批次、原件及原件清理。
    object_table('medication'), object_table('batch'),
    Table('medication_sources', (
        col('resource_id', G.PRIMARY_KEY, False),
        col('medication_id', G.REFERENCE, False),
        col('original_filename', nullable=False), col('mime_type', nullable=False), col('size_bytes', nullable=False, storage='INTEGER'),
        col('relative_path', nullable=False), col('sha256', nullable=False),
        col('source_index', nullable=False, storage='INTEGER'), col('purpose', nullable=False),
        col('is_primary', G.STATE, False, storage='INTEGER'),
        col('created_at', G.AUDIT, False),
    ), ('resource_id',), foreign_keys=(
        ForeignKey(('medication_id',), 'medications', ('medication_id',), on_delete='CASCADE'),
    ), unique_constraints=(UniqueConstraint(('medication_id', 'source_index')),),
        checks=(CheckConstraint('size_bytes > 0'), CheckConstraint('source_index >= 0'), CheckConstraint('is_primary IN (0, 1)'), CheckConstraint("purpose IN ('package', 'label', 'leaflet')")),
        indexes=(Index('medication_primary_source', ('medication_id',), unique=True, where='is_primary = 1'),)),
    Table('medication_source_cleanup_outbox', (
        col('cleanup_id', G.PRIMARY_KEY, False), col('relative_path', nullable=False), col('created_at', G.AUDIT, False),
    ), ('cleanup_id',)),
    # 用药计划。
    object_table('plan'),
    # 通用创建请求去重。
    Table('medication_requests', (
        col('actor_account_id', G.PRIMARY_KEY, False), col('request_id', G.PRIMARY_KEY, False), col('member_id', G.SCOPE),
        col('object_id', G.REFERENCE, False), col('operation', nullable=False), col('payload_hash', nullable=False), col('created_at', G.AUDIT, False),
    ), ('actor_account_id', 'request_id'), checks=(CheckConstraint("operation IN ('medication','batch','plan','sources')"), CheckConstraint("operation NOT IN ('batch','plan') OR member_id IS NOT NULL"))),
))
