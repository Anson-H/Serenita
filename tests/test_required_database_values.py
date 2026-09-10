"""Verify required data through raw SQLite as well as application validation."""
import json
import sqlite3
from contextlib import closing

import pytest

from tests.test_database_schema_contract import DATABASE_SCHEMAS
from backend.app.storage.member_lifecycle_database import MEMBER_LIFECYCLE_DATABASE
from backend.app.schemas.medication import Medication
from backend.app.schemas.report import ParsedLabResult, ParsedExaminationReport, ParsedOtherReport

TABLES = {t.name: t for d in (*DATABASE_SCHEMAS, MEMBER_LIFECYCLE_DATABASE) for t in d.tables}
AT = '2026-09-10T00:00:00+00:00'
# These are intentional empty values, independent of column implementation.
EMPTY_TEXT = {('reports', 'analysis_content'), ('body_records', 'metric'),
              ('favorites', 'source_session_id'), ('notifications', 'message'),
              ('notification_outbox', 'message')}


def valid_row(table):
    with closing(sqlite3.connect(':memory:')) as db:
        values = {c.name: db.execute('SELECT '+c.default).fetchone()[0] if c.default is not None
                  else None if c.nullable else 1 if c.storage_type == 'INTEGER'
                  else b'content' if c.storage_type == 'BLOB'
                  else '{}' if c.json_kind in ('object','container') else '[]' if c.json_kind == 'array'
                  else AT if c.name.endswith(('_at', '_on')) else 'valid'
                  for c in table.columns}
    overrides = {
        'member_grants': {'permission': 'read'},
        'model_providers': {'is_configured': 0},
        'web_providers': {'provider_id': 'exa', 'is_configured': 0},
        'web_access_settings': {'active_provider_id': 'exa'},
        'conversations': {'title': '会话'},
        'conversation_turns': {'status': 'queued'},
        'conversation_resources': {'storage_status': 'ready', 'expires_at': AT},
        'favorites': {'source_type': 'report', 'source_session_id': ''},
        'medications': {'generic_name': '药品通用名', 'prescription_type': 'unknown'},
        'medication_inventory': {'quantity': '0'},
        'medication_sources': {'purpose': 'package'},
        'medication_plans': {'start_precision': 'date', 'usage_status': 'unknown', 'timezone': 'UTC'},
        'medication_requests': {'operation': 'medication'},
        'member_lifecycle_tasks': {'operation': 'delete_files'},
        'body_records': {'kind': 'measurement', 'metric': 'weight'},
        'body_imports': {'state': 'preview'},
        'reports': {'report_type': '其它医疗报告'},
    }
    values.update(overrides.get(table.name, {}))
    if table.name in {'notifications', 'notification_outbox'}:
        values.update(notification_type='answer_completed', resource_type='conversation',
                      resource_id='session', validity_key='turn', status='pending', message='')
    return values


def insert(db, table, values):
    db.execute(f'INSERT INTO {table.name} ({",".join(values)}) VALUES ({",".join("?" for _ in values)})', tuple(values.values()))


@pytest.mark.parametrize('table', list(TABLES.values()), ids=list(TABLES))
@pytest.mark.parametrize('operation', ['insert', 'update'])
def test_all_required_columns_reject_missing_or_blank_values(table, operation):
    row = valid_row(table)
    table.validate_values(row)
    with closing(sqlite3.connect(':memory:')) as db:
        db.execute(table.create_table_sql())
        insert(db, table, row)
        for column in table.columns:
            if column.nullable:
                continue
            # SQLite allocates an INTEGER PRIMARY KEY when NULL is inserted.
            if operation == 'insert' and column.storage_type == 'INTEGER' and column.name in table.primary_key:
                continue
            bad_values = [None]
            if column.storage_type == 'TEXT' and (table.name, column.name) not in EMPTY_TEXT:
                bad_values += ['', '   ', '\t\r\n', '\u3000\u00a0']
            if column.storage_type == 'BLOB':
                bad_values += [b'']
            for bad in bad_values:
                invalid = {**row, column.name: bad}
                with pytest.raises(ValueError):
                    table.validate_values(invalid)
                with pytest.raises(sqlite3.IntegrityError):
                    if operation == 'update':
                        db.execute(f'UPDATE {table.name} SET {column.name}=?', (bad,))
                    else:
                        db.execute(f'DELETE FROM {table.name}')
                        insert(db, table, invalid)
                if operation == 'insert':
                    insert(db, table, row)


CONDITIONS = [
    ('medication_plans', {'ends_at': AT, 'end_precision': None}),
    ('medication_plans', {'ends_at': 'long_term', 'end_precision': 'date'}),
    ('medication_requests', {'operation': 'batch', 'member_id': None}),
    ('medication_requests', {'operation': 'plan', 'member_id': None}),
    ('body_records', {'kind': 'measurement', 'metric': '\t\u3000'}),
    ('body_records', {'kind': 'sleep', 'metric': '', 'ends_at': None}),
    ('body_records', {'kind': 'workout', 'metric': '', 'ends_at': None}),
    ('body_records', {'payload': '{"precision":"interval"}', 'ends_at': None}),
    ('reports', {'analysis_content': '已保存解读结果', 'analysis_updated_at': None}),
    ('medical_history', {'allergy_history': '青霉素过敏', 'allergy_history_updated_at': None}),
    ('favorites', {'source_type': 'message', 'source_session_id': '\t\u3000'}),
    ('conversation_turns', {'status': 'failed', 'error_code': None, 'error_message': None}),
    ('model_providers', {'is_configured': 1, 'encrypted_api_key': b''}),
    ('web_providers', {'is_configured': 1, 'encrypted_api_key': b''}),
    ('models', {'model_type': 'generation', 'thinking_modes': '', 'capability_profiles': '{}'}),
    ('account_preferences', {'notifications_enabled': 1, 'answer_completed_enabled': 1}),
    ('conversation_resources', {'expires_at': ''}),
    ('member_lifecycle_tasks', {'operation': 'interrupt_session', 'session_id': ''}),
]
for name in ('notifications', 'notification_outbox'):
    CONDITIONS.extend((name, {field: None}) for field in ('resource_type', 'resource_id', 'validity_key'))
    CONDITIONS.append((name, {'notification_type': 'medication_due', 'member_id': None}))


@pytest.mark.parametrize('name,changes', CONDITIONS)
@pytest.mark.parametrize('operation', ['insert', 'update'])
def test_conditional_requirements_in_application_and_raw_sql(name, changes, operation):
    table = TABLES[name]
    row = valid_row(table)
    with pytest.raises(ValueError):
        table.validate_values({**row, **changes})
    with closing(sqlite3.connect(':memory:')) as db:
        db.execute(table.create_table_sql())
        insert(db, table, row)
        with pytest.raises(sqlite3.IntegrityError):
            if operation == 'update':
                db.execute(f'UPDATE {name} SET '+','.join(f'{key}=?' for key in changes), tuple(changes.values()))
            else:
                db.execute(f'DELETE FROM {name}')
                insert(db, table, {**row, **changes})


@pytest.mark.parametrize('name,column', [('lab_items','aliases'), ('favorites','tags'),
    ('body_records','payload'), ('body_records','source_payload'), ('body_imports','payload'),
    ('models','capability_profiles'), ('medication_plans','schedule')])
@pytest.mark.parametrize('value', ['', 'null', '{invalid', '42'])
def test_json_columns_require_real_containers(name, column, value):
    table = TABLES[name]
    row = {**valid_row(table), column: value}
    with pytest.raises(ValueError):
        table.validate_values(row)
    with closing(sqlite3.connect(':memory:')) as db:
        db.execute(table.create_table_sql())
        with pytest.raises(sqlite3.IntegrityError):
            insert(db, table, row)


@pytest.mark.parametrize('value', [None, '', ' ', '\t\u3000'])
def test_generic_name_is_required_even_with_brand_name(value):
    with pytest.raises(ValueError):
        Medication.model_validate({'generic_name': value, 'brand_name': '商品名'})
    with pytest.raises(ValueError):
        Medication.model_validate({'brand_name': '商品名'})


@pytest.mark.parametrize('model,values', [
    (ParsedLabResult, dict(item_id='id', item_name_zh='指标', category_name='分类', result_text='\t\u3000')),
    (ParsedExaminationReport, dict(exam_name='\t\u3000')),
    (ParsedOtherReport, dict(report_body='\t\u3000')),
])
def test_report_application_models_reject_blank_required_content(model, values):
    with pytest.raises(ValueError):
        model.model_validate(values)


def test_legitimate_unknown_and_empty_values_remain_usable():
    cases = [
        ('medications', {'brand_name': None, 'strength': None}),
        ('medication_inventory', {'quantity': '0', 'expires_on': None}),
        ('medication_plans', {'ends_at': 'long_term', 'end_precision': None, 'dose_text': None, 'schedule': None}),
        ('reports', {'analysis_content': '', 'analysis_updated_at': None}),
        ('body_records', {'kind': 'meal', 'metric': '', 'payload': '{}'}),
        ('medical_history', {'allergy_history': None, 'allergy_history_updated_at': AT}),
        ('favorites', {'source_type': 'report', 'source_session_id': '', 'member_id': None, 'tags': '[]'}),
        ('notifications', {'notification_type': 'answer_completed', 'member_id': None, 'message': ''}),
    ]
    for name, changes in cases:
        table = TABLES[name]
        row = {**valid_row(table), **changes}
        table.validate_values(row)
        with closing(sqlite3.connect(':memory:')) as db:
            db.execute(table.create_table_sql())
            insert(db, table, row)


@pytest.mark.parametrize('key', ['turn_id', 'user_message_id', 'stream_id'])
@pytest.mark.parametrize('value', [None, '', '\t\u3000'])
def test_persisted_turn_start_rejects_missing_identity(key, value):
    from backend.app.domain.conversations.events import make_event, SessionEventCorruptionError
    data = dict(turn_id='turn', user_message_id='user', stream_id='stream')
    with pytest.raises(SessionEventCorruptionError):
        make_event('turn/start', 0, {**data, key: value})
    del data[key]
    with pytest.raises(SessionEventCorruptionError):
        make_event('turn/start', 0, data)


@pytest.mark.parametrize('name,column', [
    ('medications','brand_name'), ('medication_plans','ends_at'), ('medication_inventory','expires_on'),
    ('members','birth_date'), ('surgery_report','started_at'), ('surgery_report','ended_at'),
    ('conversations','member_id'), ('conversations','parent_session_id'),
    ('models','thinking_modes'), ('model_access_settings','chat_model_id'),
    ('reports','analysis_updated_at'), ('medical_history','allergy_history_updated_at'),
    ('background_task_checkpoints','scan_from'), ('login_sessions','revoked_at'),
])
def test_optional_metadata_accepts_null_but_rejects_blank_text(name, column):
    table = TABLES[name]
    with closing(sqlite3.connect(':memory:')) as db:
        db.execute(table.create_table_sql())
        insert(db, table, valid_row(table))
        for value in ('', '\t\r\n', '\u3000\u00a0'):
            with pytest.raises(ValueError):
                table.validate_values({column: value}, partial=True)
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(f'UPDATE {name} SET {column}=?', (value,))
