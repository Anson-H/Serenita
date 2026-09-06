from member_support import accounts as accounts
from backend.app.api.errors import error_http_status
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import threading
import time
import pytest
from backend.app.core.errors import SerenitaError
from member_support import account_id as account_id_for
from member_support import create_member, grant, report_payload
from member_support import import_report
from backend.app.application.member_service import MemberService
from backend.app.application.report_service import ReportService
from backend.app.repositories.conversation_repository import ConversationRepository
from backend.app.repositories.member_repository import MemberRepository
from backend.app.repositories.report_repository import ReportRepository
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect
from backend.app.repositories.member_data_store import MemberDataStoreParticipant, report_member_data_store_participant
from backend.app.storage.schema import Database, Table, Column, ColumnGroup


def state(client):
    response = client.get('/api/members')
    assert response.status_code == 200, response.text
    result = response.json()
    defaults = [p['member_id'] for p in result['members'] if p['is_default']]
    if result['members']:
        assert result['default_member_id'] is not None
        assert defaults == [result['default_member_id']]
    else:
        assert defaults == []
        assert result['default_member_id'] is None
        assert result['last_member_id'] is None
        assert result['initial_member_id'] is None
    return result


def prefer(client, **values):
    response = client.patch('/api/account-settings/member-preferences', json=values)
    assert response.status_code == 200, response.text
    return response.json()


def test_member_preference_waits_for_concurrent_configuration_write(accounts, monkeypatch):
    owner, *_ = accounts
    actor_id = owner.get("/api/auth/session").json()["account_id"]
    member_id = state(owner)['default_member_id']
    repository = MemberRepository()
    attached = threading.Event()
    attach_config = repository._attach_config_database

    def notify_attachment(*args, **kwargs):
        result = attach_config(*args, **kwargs)
        attached.set()
        return result

    monkeypatch.setattr(repository, '_attach_config_database', notify_attachment)
    with connect(app_paths().config_db(actor_id)) as writer:
        writer.execute('BEGIN IMMEDIATE')
        writer.execute('UPDATE member_preferences SET startup_mode = startup_mode')
        with ThreadPoolExecutor(max_workers=1) as executor:
            saving = executor.submit(repository.save_preferences, actor_id, last_member_id=member_id)
            try:
                assert attached.wait(2), 'preference request did not start'
                # A concurrent configuration save must delay this write, not fail
                # during the later upgrade from a read snapshot to a write lock.
                with pytest.raises(TimeoutError):
                    saving.result(timeout=0.1)
            finally:
                writer.commit()
            saving.result(timeout=3)
    assert state(owner)['last_member_id'] == member_id


def test_default_creation_update_and_startup_are_independent(accounts):
    owner, *_ = accounts
    first = state(owner)['default_member_id']
    assert owner.get(f'/api/members/{first}').json()['member_name'] == '本人'
    created = owner.post('/api/members', json={'member_name': '家人', 'set_as_default': True}).json()
    second = created['member_id']
    assert created['is_default']
    assert state(owner)['default_member_id'] == second
    prefer(owner, last_member_id=first)
    assert state(owner)['initial_member_id'] == first
    assert prefer(owner, startup_mode='default')['initial_member_id'] == second
    response = owner.patch(f'/api/members/{first}', json={'member_name': '新名称', 'set_as_default': True})
    assert response.status_code == 200 and response.json()['is_default']
    assert state(owner)['default_member_id'] == first
    owner.patch(f'/api/members/{first}', json={'member_name': '新名称', 'set_as_default': False})
    assert state(owner)['default_member_id'] == first
    for invalid in (None, '', '   '):
        assert owner.patch('/api/account-settings/member-preferences', json={'default_member_id': invalid}).status_code == 422
    assert owner.patch('/api/account-settings/member-preferences', json={'startup_mode': 'self'}).status_code == 422
    assert owner.patch('/api/account-settings/member-preferences', json={'default_member_id': 'missing'}).status_code == 403
    assert state(owner)['default_member_id'] == first


def test_shared_read_only_default_is_private_and_revocation_replaces_it(accounts):
    owner, reader, editor = accounts
    target = create_member(owner)
    own_default = state(owner)['default_member_id']
    reader_first = state(reader)['default_member_id']
    create_member(reader, '第二位')
    grants = grant(owner, target, 'reader', 'read')
    grant(owner, target, 'editor', 'edit')
    before_owner, before_reader = state(owner)['access_revision'], state(reader)['access_revision']
    prefer(reader, default_member_id=target, last_member_id=target, startup_mode='default')
    assert state(owner)['default_member_id'] == own_default
    assert state(owner)['access_revision'] == before_owner
    assert state(reader)['access_revision'] > before_reader
    assert not editor.get(f'/api/members/{target}').json()['is_default']
    assert reader.patch(f'/api/members/{target}', json={'member_name': '越权', 'set_as_default': True}).status_code == 403
    assert reader.delete(f'/api/members/{target}').status_code == 403
    assert editor.delete(f'/api/members/{target}').status_code == 403
    assert reader.post(f'/api/members/{target}/reports', json=report_payload()).status_code == 403
    assert reader.delete(f'/api/members/{reader_first}').status_code == 200
    remaining = next(p['member_id'] for p in state(reader)['members'] if p['is_owned'])
    assert reader.delete(f'/api/members/{remaining}').status_code == 200
    assert state(reader)['default_member_id'] == target
    revoked = owner.delete(f"/api/account-settings/member-grants/{target}/{grants[0]['account_id']}")
    assert revoked.status_code == 200
    assert state(reader)['members'] == []
    grant(owner, target, 'reader', 'read')
    assert state(reader)['default_member_id'] == target
    assert state(reader)['last_member_id'] is None


def test_default_deletion_replaces_every_affected_account_and_preserves_valid_choices(accounts):
    owner, reader, editor = accounts
    original = state(owner)['default_member_id']
    second = create_member(owner)
    third = create_member(owner)
    # Equal timestamps have a stable member-id tie break.
    with connect(app_paths().auth_db) as c:
        c.execute('UPDATE member_ownerships SET created_at = ? WHERE member_id IN (?, ?)', ('2026-01-01', second, third))
    grant(owner, original, 'reader', 'read')
    grant(owner, original, 'editor', 'edit')
    reader_own = state(reader)['default_member_id']
    editor_own = state(editor)['default_member_id']
    prefer(reader, default_member_id=original, last_member_id=original)
    prefer(editor, last_member_id=original)
    prefer(owner, last_member_id=third)
    response = owner.delete(f'/api/members/{original}')
    assert response.status_code == 200, response.text
    assert response.json()['pending_file_cleanup'] == 0
    assert state(owner)['default_member_id'] == min(second, third)
    assert state(owner)['last_member_id'] == third
    assert state(reader)['default_member_id'] == reader_own
    assert state(reader)['last_member_id'] == reader_own
    assert state(editor)['default_member_id'] == editor_own
    assert state(editor)['last_member_id'] == editor_own
    assert owner.get('/api/account-settings/member-grants').json()['grants'] == []
    assert owner.delete(f'/api/members/{original}').status_code == 403


def test_create_and_update_roll_back_with_default_setting(accounts):
    owner, *_ = accounts
    original = state(owner)['default_member_id']
    target = create_member(owner, '原名称')
    repository = MemberRepository()
    with connect(app_paths().config_db(account_id_for('owner'))) as c:
        c.execute("""CREATE TRIGGER reject_default BEFORE UPDATE OF default_member_id ON member_preferences
                     BEGIN SELECT RAISE(ABORT, 'simulated preference failure'); END""")
    before = {p['member_id'] for p in state(owner)['members']}
    with pytest.raises(sqlite3.IntegrityError):
        repository.create(account_id_for('owner'), {'member_name': '不应创建'}, set_as_default=True)
    access = repository.resolve(account_id_for('owner'), target)
    with pytest.raises(sqlite3.IntegrityError):
        repository.update(access, {'member_name': '不应保存'}, set_as_default=True)
    assert {p['member_id'] for p in state(owner)['members']} == before
    assert owner.get(f'/api/members/{target}').json()['member_name'] == '原名称'
    assert state(owner)['default_member_id'] == original
    with connect(app_paths().members_db(account_id_for('owner'))) as c:
        assert {row[0] for row in c.execute('SELECT member_id FROM members')} == before


def test_concurrent_preferences_and_deletions_preserve_invariants(accounts):
    owner, *_ = accounts
    first = state(owner)['default_member_id']
    second = create_member(owner)
    barrier = threading.Barrier(2)
    def choose(member):
        barrier.wait()
        MemberRepository().save_preferences(account_id_for('owner'), default_member_id=member)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(choose, [first, second]))
    assert state(owner)['default_member_id'] in (first, second)
    barrier = threading.Barrier(2)
    def remove(member):
        barrier.wait()
        try:
            MemberRepository().delete(account_id_for('owner'), member)
            return 200
        except SerenitaError as error:
            return error_http_status(error)
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(remove, [first, second])) == [200, 200]
    assert state(owner)['members'] == []


def test_delete_waits_for_report_write_then_blocks_further_writes(accounts):
    owner, *_ = accounts
    target = create_member(owner)
    service = ReportService.for_member(account_id_for('owner'), target)
    started, finished = threading.Event(), threading.Event()
    failures = []
    def remove():
        started.set()
        try:
            MemberService().delete_member(account_id_for('owner'), target)
        except Exception as error:
            failures.append(error)
        finally:
            finished.set()
    with service.scope.guard(write=True):
        thread = threading.Thread(target=remove)
        thread.start()
        assert started.wait(1)
        time.sleep(.05)
        assert not finished.is_set()
        service.create_manual_report(target, report=report_payload())
    thread.join(3)
    assert finished.is_set() and failures == []
    with pytest.raises(SerenitaError):
        service.create_manual_report(target, report=report_payload())
    with connect(app_paths().reports_db(account_id_for('owner'))) as c:
        assert c.execute('SELECT COUNT(*) FROM reports WHERE member_id = ?', (target,)).fetchone()[0] == 0


def test_deleted_member_cleanup_and_history_survive_without_cross_member_loss(accounts, monkeypatch):
    owner, reader, _ = accounts
    target, other = create_member(owner), create_member(owner)
    grant(owner, target, 'reader', 'read')
    attachment = app_paths().account_root(account_id_for('owner')) / 'conversations/attachments/source.jpg'
    attachment.parent.mkdir(parents=True, exist_ok=True)
    attachment.write_bytes(b'\xff\xd8\xfftest')
    deleted_report = import_report('owner', target, attachment=attachment)
    retained_report = import_report('owner', other, attachment=attachment)
    target_service = ReportService.for_member(account_id_for('owner'), target)
    source = reader.get(f"/api/members/{target}/reports/{deleted_report['report_id']}").json()['sources'][0]
    original_path, _, _ = target_service.source_download(target, deleted_report['report_id'], source['resource_id'])
    repository = ReportRepository(account_id_for('owner'))
    unlinked = app_paths().report_attachment_path(
        account_id_for('owner'), 'unlinked', 'jpg'
    )
    unlinked.write_bytes(b'\xff\xd8\xffunlinked')
    repository.register_source_file(target, resource_id='unlinked', relative_path=str(unlinked.relative_to(app_paths().account_root(account_id_for('owner')))),
        mime_type='image/jpeg', size_bytes=unlinked.stat().st_size, sha256='unlinked', source_kind='photo')
    session_id = ConversationRepository().ensure_session(account_id_for('reader'), member_id=target)
    favorite = reader.post('/api/favorites', json={'source_type': 'report', 'member_id': target, 'source_id': deleted_report['report_id']})
    assert favorite.status_code == 200, favorite.text
    with connect(app_paths().reports_db(account_id_for('owner'))) as c:
        dictionary_before = [tuple(r) for r in c.execute('SELECT * FROM lab_items')]
    unlink = Path.unlink
    blocked = {original_path.resolve(), unlinked.resolve()}
    def fail_cleanup(path, *args, **kwargs):
        if path.resolve() in blocked:
            raise OSError('simulated file busy')
        return unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', fail_cleanup)
    response = owner.delete(f'/api/members/{target}')
    assert response.status_code == 200, response.text
    assert response.json()['pending_file_cleanup'] == 2
    assert original_path.exists() and unlinked.exists()
    assert reader.get(source['download_url']).status_code == 403
    history = reader.get(f'/api/conversations/{session_id}')
    assert history.status_code == 200, history.text
    assert history.json()['member_id'] is None and history.json()['access_state'] == 'available'
    assert history.json()['fork_available'] is False
    retained_favorite = reader.get('/api/favorites/' + favorite.json()['favorite_id'])
    assert retained_favorite.status_code == 200
    assert retained_favorite.json()['source_available'] is False
    assert retained_favorite.json()['content_snapshot'] == favorite.json()['content_snapshot']
    blocked.clear()
    # A later report operation retries account-scoped cleanup even though the
    # deleted member can no longer be used as an access scope.
    assert owner.get(f'/api/members/{other}/reports').status_code == 200
    assert not original_path.exists() and not unlinked.exists()
    assert repository.file_cleanup_count(target) == 0
    assert attachment.exists()
    assert owner.get(f"/api/members/{other}/reports/{retained_report['report_id']}").status_code == 200
    with connect(app_paths().reports_db(account_id_for('owner'))) as c:
        assert [tuple(r) for r in c.execute('SELECT * FROM lab_items')] == dictionary_before
        assert c.execute('PRAGMA foreign_key_check').fetchall() == []


def test_registered_peer_store_joins_member_hard_delete(accounts):
    owner, *_ = accounts
    owner_account_id = account_id_for("owner")
    target = create_member(owner, "待删除")
    retained = create_member(owner, "保留")
    peer_path = (
        app_paths().account_root(owner_account_id)
        / "future-domain"
        / "db_storage"
        / "future.db"
    )
    peer_path.parent.mkdir(parents=True, exist_ok=True)
    peer_schema = Database("future.db", (Table("entries", (
        Column("member_id", "TEXT", ColumnGroup.PRIMARY_KEY),
        Column("payload", "TEXT", ColumnGroup.DATA, nullable=False),
    ), primary_key=("member_id",)),))
    with sqlite3.connect(peer_path) as connection:
        peer_schema.create(connection)
        connection.executemany(
            "INSERT INTO entries(member_id, payload) VALUES (?, ?)",
            ((target, "remove"), (retained, "keep")),
        )

    after_commit: list[tuple[str, str]] = []

    def validate_existing(owner_id: str) -> None:
        assert owner_id == owner_account_id
        assert peer_schema.validate_existing(peer_path)


    def delete_member_data(connection, schema_alias, owner_id, member_id):
        assert owner_id == owner_account_id
        connection.execute(
            f'DELETE FROM "{schema_alias}".entries WHERE member_id = ?',
            (member_id,),
        )

    participant = MemberDataStoreParticipant(
        name="future-domain",
        schema_alias="future_data",
        path_for_owner=lambda owner_id: peer_path,
        validate_existing=validate_existing,
        delete_member_data=delete_member_data,
    )
    repository = MemberRepository(
        data_stores=(report_member_data_store_participant(), participant)
    )

    result = MemberService(repository=repository, after_delete=(lambda owner_id, member_id: after_commit.append((owner_id, member_id)),)).delete_member(
        owner_account_id, target
    )

    assert result["deleted"] is True
    assert after_commit == [(owner_account_id, target)]
    with sqlite3.connect(peer_path) as connection:
        assert connection.execute(
            "SELECT member_id FROM entries ORDER BY member_id"
        ).fetchall() == [(retained,)]
    with sqlite3.connect(app_paths().members_db(owner_account_id)) as connection:
        assert connection.execute(
            "SELECT member_id FROM members WHERE member_id = ?", (target,)
        ).fetchone() is None


def test_existing_uninitialized_peer_store_blocks_member_delete(accounts):
    owner, *_ = accounts
    owner_account_id = account_id_for("owner")
    target = create_member(owner, "不能删除")
    report_path = app_paths().reports_db(owner_account_id)
    report_path.touch()

    response = owner.delete(f"/api/members/{target}")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "UNSUPPORTED_SCHEMA"
    assert owner.get(f"/api/members/{target}").status_code == 200
    assert report_path.is_file() and report_path.stat().st_size == 0
