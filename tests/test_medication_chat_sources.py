"""Chat originals use the medication store and verified attachment boundary."""
from uuid import uuid4

import pytest

from backend.app.agent_runtime.context import AgentContext
from backend.app.core.attachment_content import AttachmentContent
from backend.app.core.errors import SerenitaError
from backend.app.plugins.medication.registry import build_tools
from backend.app.plugins.runtime_context import PluginRuntimeContext
from member_support import accounts, account_id, create_member, grant
from tests.test_medication_sources import catalog_drug, add_source
from tests.test_medications import execute_medication_tool, url


def source_tool(actor, member, attachments, *, name='add_medication_sources'):
    context = PluginRuntimeContext(
        account_id=account_id(actor), member_id=member, event_recorder=lambda _: None,
        conversation_attachment_reader=attachments.__getitem__,
    )
    return next(tool for tool in build_tools(runtime_context=context) if tool.name == name)


def payload(medication_id, *resources):
    return {'medication_id': medication_id, 'request_id': str(uuid4()),
            'sources': [{'resource_id': resource, 'purpose': 'package'} for resource in resources]}


def test_chat_appends_multiple_originals_and_keeps_existing_primary(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    medication = catalog_drug(owner)
    primary = add_source(owner, medication['medication_id'], 'Existing original').json()['sources'][0]
    files = {'photo': AttachmentContent('photo', 'package.png', 'image/png', b'\x89PNG\r\n\x1a\npackage'),
             'leaflet': AttachmentContent('leaflet', 'leaflet.txt', 'text/plain', b'New leaflet')}
    tool = source_tool('owner', member, files)
    arguments = payload(medication['medication_id'], 'photo', 'leaflet')
    arguments['sources'][1]['purpose'] = 'leaflet'
    result = execute_medication_tool(tool, arguments, visible=files)
    saved = result.output
    assert [source['source_index'] for source in saved['sources']] == [0, 1, 2]
    assert [source['is_primary'] for source in saved['sources']] == [1, 0, 0]
    assert saved['sources'][0]['resource_id'] == primary['resource_id']
    assert saved['sources'][1]['resource_id'] != 'photo'
    assert saved['sources'][2]['purpose'] == 'leaflet'
    assert execute_medication_tool(tool, arguments, visible=files).output == saved
    assert saved['batches'] == []
    assert owner.get(url(member, 'medication-plans')).json()['items'] == []
    expected = files['photo'].content_bytes
    files.clear()
    path = '/api/medication-catalog/'+medication['medication_id']+'/source-files/'+saved['sources'][1]['resource_id']
    assert owner.get(path).content == expected
    assert result.effects['resource_refs'][0]['resource_id'] == medication['medication_id']


@pytest.mark.parametrize('problem', ['duplicate', 'invalid', 'invisible'])
def test_failed_batch_never_partially_saves_originals(accounts, problem):
    owner, *_ = accounts
    member = create_member(owner)
    medication = catalog_drug(owner)
    add_source(owner, medication['medication_id'], 'Duplicate')
    files = {'new': AttachmentContent('new', 'new.txt', 'text/plain', b'New original'),
             'bad': AttachmentContent('bad', 'bad.txt', 'text/plain', b'Duplicate')}
    if problem == 'invalid':
        files['bad'] = AttachmentContent('bad', 'bad.png', 'image/png', b'Invalid image')
    visible = files if problem != 'invisible' else {'new': files['new']}
    tool = source_tool('owner', member, files)
    arguments = payload(medication['medication_id'], 'new', 'bad')
    with pytest.raises((SerenitaError, ValueError)):
        execute_medication_tool(tool, arguments, visible=visible)
    saved = owner.get('/api/medication-catalog/'+medication['medication_id']).json()
    assert len(saved['sources']) == 1


def test_binding_rejects_hidden_attachment_even_without_schema_validation(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    tool = source_tool('owner', member, {})
    context = AgentContext(account_id=account_id('owner'), member_id=member, task_type='conversation')
    with pytest.raises(PermissionError):
        tool.bind_runtime_arguments(payload('drug', 'hidden'), context=context, observations=[])


@pytest.mark.parametrize('permission', ['read', 'edit'])
def test_shared_member_cannot_append_account_catalog_originals(accounts, permission):
    owner, *_ = accounts
    member = create_member(owner)
    medication = catalog_drug(owner)
    grant(owner, member, 'reader', permission)
    files = {'file': AttachmentContent('file', 'file.txt', 'text/plain', b'Private original')}
    with pytest.raises(SerenitaError):
        execute_medication_tool(source_tool('reader', member, files), payload(medication['medication_id'], 'file'), visible=files)
    assert owner.get('/api/medication-catalog/'+medication['medication_id']).json()['sources'] == []


def test_create_medication_saves_information_and_originals_in_one_call(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    files = {'package': AttachmentContent('package', 'package.txt', 'text/plain', b'Package original'),
             'leaflet': AttachmentContent('leaflet', 'leaflet.txt', 'text/plain', b'Leaflet original')}
    tool = source_tool('owner', member, files, name='create_medication')
    arguments = {'generic_name': 'Created with originals', 'strength': '5 mg', 'request_id': str(uuid4()),
                 'sources': [{'resource_id': 'package', 'purpose': 'package'},
                             {'resource_id': 'leaflet', 'purpose': 'leaflet'}]}
    saved = execute_medication_tool(tool, arguments, visible=files).output
    assert saved['generic_name'] == 'Created with originals'
    assert [source['is_primary'] for source in saved['sources']] == [1, 0]
    assert [source['purpose'] for source in saved['sources']] == ['package', 'leaflet']
    for original, stored in zip(files.values(), saved['sources']):
        response = owner.get('/api/medication-catalog/'+saved['medication_id']+'/source-files/'+stored['resource_id'])
        assert response.content == original.content_bytes
    assert execute_medication_tool(tool, arguments, visible=files).output == saved
    files['package'] = AttachmentContent('package', 'package.txt', 'text/plain', b'Changed original')
    with pytest.raises(SerenitaError):
        execute_medication_tool(tool, arguments, visible=files)
    assert owner.get('/api/medication-catalog').json()['total'] == 1
    assert saved['batches'] == []
    assert owner.get(url(member, 'medication-plans')).json()['items'] == []


@pytest.mark.parametrize('problem', ['duplicate', 'invalid', 'invisible', 'identity', 'file_write', 'request_write'])
def test_create_medication_failure_leaves_no_information_files_or_request(accounts, monkeypatch, problem):
    from backend.app.repositories.medication_source_repository import MedicationSourceRepository
    from backend.app.repositories.medication_repository import MedicationRepository
    from backend.app.storage.paths import app_paths
    from backend.app.storage.sqlite import connect
    owner, *_ = accounts
    member = create_member(owner)
    files = {'first': AttachmentContent('first', 'first.txt', 'text/plain', b'First original'),
             'second': AttachmentContent('second', 'second.txt', 'text/plain', b'Second original')}
    if problem == 'duplicate':
        files['second'] = AttachmentContent('second', 'second.txt', 'text/plain', b'First original')
    elif problem == 'invalid':
        files['second'] = AttachmentContent('second', 'second.png', 'image/png', b'Invalid image')
    elif problem == 'file_write':
        ensure = MedicationSourceRepository.ensure

        def fail_after_second_write(self, db, member, medication_id, source, position, created):
            result = ensure(self, db, member, medication_id, source, position, created)
            if position == 1:
                raise OSError('Injected failure after second file')
            return result

        monkeypatch.setattr(MedicationSourceRepository, 'ensure', fail_after_second_write)
    elif problem == 'request_write':
        def fail_record(*args, **kwargs):
            raise OSError('Injected request persistence failure')
        monkeypatch.setattr(MedicationRepository, 'record_request', fail_record)
    arguments = {'generic_name': None if problem == 'identity' else 'Failed creation', 'request_id': str(uuid4()),
                 'sources': [{'resource_id': key, 'purpose': 'package'} for key in files]}
    visible = {'first': files['first']} if problem == 'invisible' else files
    tool = source_tool('owner', member, files, name='create_medication')
    with pytest.raises((SerenitaError, ValueError, OSError)):
        execute_medication_tool(tool, arguments, visible=visible)
    assert owner.get('/api/medication-catalog').json()['items'] == []
    paths = app_paths()
    actor = account_id('owner')
    with connect(paths.medications_db(actor)) as db:
        assert db.execute('SELECT count(*) FROM medication_sources').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM medication_requests').fetchone()[0] == 0
    root = paths.medication_files_dir(actor)
    assert not root.exists() or not list(root.iterdir())
