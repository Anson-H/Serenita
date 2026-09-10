"""Settings-owned medication information and member inventory boundaries."""
from uuid import uuid4
import pytest
from member_support import accounts, account_id, create_member, grant
from backend.app.application.services import ApplicationServices
from backend.app.core.errors import SerenitaError
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect
from tests.test_medications import post, url, plan, execute_medication_tool


def catalog_drug(client, **fields):
    response = post(client, '/api/medication-catalog', {'generic_name': '目录药品', **fields})
    assert response.status_code == 201, response.text
    return response.json()


def add_source(client, medication_id, text='药品原件'):
    return client.post(f'/api/medication-catalog/{medication_id}/source-files',
        files={'files': ('原件.txt', text, 'text/plain')}, headers={'Idempotency-Key': str(uuid4())})


def test_settings_catalog_is_shared_by_owner_members_and_member_routes_are_read_only(accounts):
    owner, reader, *_ = accounts
    first, second = create_member(owner), create_member(owner)
    med = catalog_drug(owner, strength='5 mg')
    assert 'member_id' not in med and 'batches' not in med
    for member in (first, second):
        target = url(member, key=med['medication_id'])
        assert owner.get(target).json()['strength'] == '5 mg'
        assert post(owner, url(member), {'generic_name': '非法添加'}).status_code == 405
        assert owner.patch(target, json={'strength': '10 mg'}).status_code == 405
        assert owner.delete(target).status_code == 405
        assert owner.post(target+'/source-files',files={'files':('非法.txt','文本','text/plain')}).status_code == 404
    assert reader.get('/api/medication-catalog').json()['items'] == []
    grant(owner, first, 'reader', 'read')
    assert reader.get(url(first,key=med['medication_id'])).status_code == 200
    assert reader.get(url(second,key=med['medication_id'])).status_code == 403
    assert reader.patch('/api/medication-catalog/'+med['medication_id'],json={'notes':'非法'}).status_code == 404
    assert owner.patch('/api/medication-catalog/'+med['medication_id'],json={'strength':'10 mg'}).status_code == 200
    assert reader.get(url(first,key=med['medication_id'])).json()['strength'] == '10 mg'
    assert owner.get(url(second,key=med['medication_id'])).json()['strength'] == '10 mg'


def test_inventory_is_member_scoped_and_catalog_deletion_protects_references(accounts):
    owner, reader, *_ = accounts
    first, second = create_member(owner), create_member(owner)
    med = catalog_drug(owner)
    batches = []
    for member, quantity in ((first,'2'),(second,'8')):
        response = post(owner, url(member,key=med['medication_id'])+'/batches', {'quantity':quantity,'expires_on':'2027-01-01'})
        assert response.status_code == 201, response.text
        batches.append(response.json())
    for member, quantity in ((first,'2'),(second,'8')):
        value = owner.get(url(member,key=med['medication_id'])).json()
        assert [batch['quantity'] for batch in value['batches']] == [quantity]
        assert len(owner.get(url(member),params={'inventory_only':True}).json()['items']) == 1
    grant(owner,first,'reader','read')
    assert post(reader,url(first,key=med['medication_id'])+'/batches',{'quantity':'1'}).status_code == 403
    assert owner.delete('/api/medication-catalog/'+med['medication_id']).status_code == 409
    assert owner.patch(url(second,key=med['medication_id'])+'/batches/'+batches[0]['medication_batch_id'],json={'quantity':'0'}).status_code == 404
    assert owner.delete(url(first,key=med['medication_id'])+'/batches/'+batches[0]['medication_batch_id']).status_code == 200
    assert owner.get(url(first),params={'inventory_only':True}).json()['items'] == []
    assert len(owner.get(url(second,key=med['medication_id'])).json()['batches']) == 1
    assert owner.get('/api/medication-catalog/'+med['medication_id']).status_code == 200


def test_deleting_member_keeps_catalog_originals_and_other_member_inventory(accounts):
    owner, *_ = accounts
    first, second = create_member(owner), create_member(owner)
    med = catalog_drug(owner)
    original = add_source(owner,med['medication_id']).json()['sources'][0]
    for member in (first,second):
        assert post(owner,url(member,key=med['medication_id'])+'/batches',{'quantity':'1'}).status_code == 201
    assert owner.delete('/api/members/'+first).status_code == 200
    assert owner.get('/api/medication-catalog/'+med['medication_id']).status_code == 200
    assert owner.get('/api/medication-catalog/'+med['medication_id']+'/source-files/'+original['resource_id']).text == '药品原件'
    assert len(owner.get(url(second,key=med['medication_id'])).json()['batches']) == 1
    assert owner.delete('/api/members/'+second).status_code == 200
    assert owner.delete('/api/medication-catalog/'+med['medication_id']).status_code == 200
    ApplicationServices().medications.drain_files(account_id('owner'))
    assert list(app_paths().medication_files_dir(account_id('owner')).iterdir()) == []


def test_plan_uses_catalog_without_stock_and_does_not_cascade_on_catalog_deletion(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    med = catalog_drug(owner)
    saved = plan(owner,member,med)
    assert owner.get(url(member),params={'inventory_only':True}).json()['items'] == []
    assert owner.delete('/api/medication-catalog/'+med['medication_id']).status_code == 409
    assert owner.patch('/api/medication-catalog/'+med['medication_id'],json={'generic_name':'新名称'}).status_code == 200
    assert owner.get(url(member,'medication-plans',saved['medication_plan_id'])).json()['medication_identity']['generic_name'] == '新名称'


def test_catalog_creation_and_inventory_tools_have_separate_writes(accounts):
    from backend.app.plugins.medication.registry import build_tools
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    owner, *_ = accounts
    member = create_member(owner)
    med = catalog_drug(owner)
    context = PluginRuntimeContext(account_id=account_id('owner'), member_id=member,event_recorder=lambda event:None)
    tools = {tool.name:tool for tool in build_tools(runtime_context=context)}
    assert 'create_medication' in tools
    assert not {'update_medication','delete_medication','merge_medication','link_medication_sources','attach_medication_file'} & tools.keys()
    created = execute_medication_tool(tools['create_medication_batch'], {'medication_id':med['medication_id'],'quantity':'1.50','request_id':str(uuid4())}).output
    assert created['quantity'] == '1.5'
    with pytest.raises(ValueError):
        execute_medication_tool(tools['update_medication_batch'], {'medication_batch_id':created['medication_batch_id'],'generic_name':'非法'})
    result = execute_medication_tool(tools['read_medication_inventory'],{'medication_id':med['medication_id']}).output
    assert result['batches'][0]['quantity'] == '1.5'
    assert execute_medication_tool(tools['read_medication_information'],{}).output['items'][0]['medication_id'] == med['medication_id']
    service=ApplicationServices().medications
    with pytest.raises(SerenitaError):service.save(account_id('owner'),member,'medication',{'notes':'非法'},object_id=med['medication_id'])
    with pytest.raises(SerenitaError):service.add_sources(account_id('owner'),member,med['medication_id'],[],str(uuid4()))


def test_settings_sources_are_atomic_deduplicated_and_owned_by_one_drug(accounts):
    owner, *_ = accounts
    first, second = catalog_drug(owner), catalog_drug(owner,generic_name='另一药品')
    saved = add_source(owner,first['medication_id']); assert saved.status_code == 201,saved.text
    reference = saved.json()['sources'][0]
    base = '/api/medication-catalog/'+first['medication_id']
    duplicate = owner.post(base+'/source-files',files=[('files',('新.txt','添加','text/plain')),('files',('重复.txt','药品原件','text/plain'))],headers={'Idempotency-Key':str(uuid4())})
    assert duplicate.status_code == 400
    assert len(owner.get(base).json()['sources']) == 1
    assert owner.get('/api/medication-catalog/'+second['medication_id']+'/source-files/'+reference['resource_id']).status_code == 404
    assert add_source(owner,first['medication_id'],'第二份原件').status_code == 201
    assert [row['is_primary'] for row in owner.get(base).json()['sources']] == [1,0]
    with connect(app_paths().medications_db(account_id('owner'))) as db:
        assert 'member_id' not in {row[1] for row in db.execute('PRAGMA table_info(medications)')}
        assert 'member_id' not in {row[1] for row in db.execute('PRAGMA table_info(medication_sources)')}
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('values',[{}, {'generic_name':None,'brand_name':None},{'generic_name':'药品','leaflet_url':'javascript:bad'}, {'generic_name':'药品','unknown':'bad'}])
def test_catalog_information_validation(accounts,values):
    assert post(accounts[0],'/api/medication-catalog',values).status_code == 400


def test_chat_catalog_creation_is_idempotent_without_inventory_or_plan(accounts):
    from backend.app.plugins.medication.registry import build_tools
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    owner, *_ = accounts
    member, other = create_member(owner), create_member(owner)
    tools = {tool.name: tool for tool in build_tools(runtime_context=PluginRuntimeContext(
        account_id=account_id('owner'), member_id=member, event_recorder=lambda _: None))}
    query = tools['read_medication_information']
    assert execute_medication_tool(query, {'query': 'Chat medicine'}).output['items'] == []
    payload = {'generic_name': 'Chat medicine', 'strength': '5 mg', 'request_id': str(uuid4())}
    result = execute_medication_tool(tools['create_medication'], payload)
    saved = result.output
    assert saved['package_specification'] is None and saved['prescription_type'] == 'unknown'
    assert execute_medication_tool(tools['create_medication'], payload).output == saved
    with pytest.raises(SerenitaError):
        execute_medication_tool(tools['create_medication'], {**payload, 'strength': '10 mg'})
    assert execute_medication_tool(query, {'query': 'Chat medicine'}).output['total'] == 1
    assert owner.get('/api/medication-catalog/'+saved['medication_id']).json()['generic_name'] == 'Chat medicine'
    assert result.effects['resource_refs'][0]['resource_id'] == saved['medication_id']
    for scope in (member, other):
        assert owner.get(url(scope, key=saved['medication_id'])).json()['batches'] == []
        assert owner.get(url(scope, 'medication-plans')).json()['items'] == []


@pytest.mark.parametrize('permission', ['read', 'edit'])
def test_shared_member_permissions_do_not_grant_catalog_creation(accounts, permission):
    from backend.app.plugins.medication.registry import build_tools
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    owner, reader, _ = accounts
    member = create_member(owner)
    grant(owner, member, 'reader', permission)
    tools = {tool.name: tool for tool in build_tools(runtime_context=PluginRuntimeContext(
        account_id=account_id('reader'), member_id=member, event_recorder=lambda _: None))}
    with pytest.raises(SerenitaError):
        execute_medication_tool(tools['create_medication'], {'generic_name': 'Forbidden', 'request_id': str(uuid4())})
    assert owner.get('/api/medication-catalog').json()['items'] == []
    assert reader.get('/api/medication-catalog').json()['items'] == []


@pytest.mark.parametrize('exists', [False, True])
def test_catalog_skill_returns_query_and_creation_observations_to_harness(accounts, exists):
    import json
    from backend.app.core.tabular_json import decode_tabular_json
    from backend.app.agent_runtime.context import AgentContext
    from backend.app.agent_runtime.model_types import AssistantModelOutput
    from backend.app.plugins.medication.registry import build_skills, build_tools
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    from tests.agent_support import HarnessDriver, call, runtime
    owner, *_ = accounts
    member = create_member(owner)
    if exists:
        catalog_drug(owner, generic_name='Observed medicine')
    actor = account_id('owner')
    tools = build_tools(runtime_context=PluginRuntimeContext(
        account_id=actor, member_id=member, event_recorder=lambda _: None))
    outputs = [
        call('load', 'load_skill', name='medication-catalog'),
        call('load-query', 'load_skill', name='medication-query'),
        call('query', 'read_medication_information', query='Observed medicine'),
    ]
    if not exists:
        outputs.append(call('create', 'create_medication', generic_name='Observed medicine', request_id='observed-create'))
    outputs.append(AssistantModelOutput(content='Would you like inventory management or a medication plan?'))
    driver = HarnessDriver(*outputs)
    result = runtime(skills=build_skills(), tools=tools).execute(
        AgentContext(account_id=actor, member_id=member, task_type='conversation', input_text='Observed medicine'),
        derive_messages=driver.derive, complete_model=driver.complete, on_event=driver.record)
    assert result.output['status'] == 'completed'
    initial_tools = {tool.name for tool in driver.requests[0].tools}
    loaded_tools = {tool.name for tool in driver.requests[1].tools}
    assert loaded_tools - initial_tools == {'create_medication', 'add_medication_sources'}
    assert {tool.name for tool in driver.requests[2].tools} - loaded_tools == {
        'read_medication_information', 'read_medication_inventory', 'read_medication_batch',
        'read_medication_plan',
    }
    observed_query = next(message for message in driver.requests[3].messages
                          if message.get('name') == 'read_medication_information')
    assert bool(decode_tabular_json(json.loads(observed_query['content'])['output'])['items']) == exists
    if not exists:
        observed_create = next(message for message in driver.requests[-1].messages
                               if message.get('name') == 'create_medication')
        assert decode_tabular_json(json.loads(observed_create['content'])['output'])['medication_id']
    assert owner.get('/api/medication-catalog').json()['total'] == 1
    assert owner.get(url(member), params={'inventory_only': True}).json()['items'] == []
    assert owner.get(url(member, 'medication-plans')).json()['items'] == []


def test_medication_information_automatically_continues_with_page_resource_refs(accounts):
    from backend.app.plugins.medication.registry import build_tools
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    owner, *_ = accounts
    member = create_member(owner)
    saved = [catalog_drug(owner, generic_name=f'分页药品{index}') for index in range(25)]
    tool = next(tool for tool in build_tools(runtime_context=PluginRuntimeContext(
        account_id=account_id('owner'), member_id=member, event_recorder=lambda _: None,
    )) if tool.name == 'read_medication_information')
    first = execute_medication_tool(tool, {'query': '分页药品'})
    second = first.next_page()
    assert len(first.output['items']) == 24 and len(second.output['items']) == 1
    assert {item['medication_id'] for page in (first, second) for item in page.output['items']} == {item['medication_id'] for item in saved}
    assert second.output['pagination'] == {'page': 2, 'complete': True}
    assert second.next_page is None
    for page in (first, second):
        assert {ref['resource_id'] for ref in page.effects['resource_refs']} == {item['medication_id'] for item in page.output['items']}


def test_generic_name_required_for_create_update_and_tool_parameters(accounts):
    owner, *_ = accounts
    for values in ({'brand_name': '只有商品名'}, *({'generic_name': value, 'brand_name': '商品名'} for value in (None, '', ' ', '\t\u3000'))):
        response = post(owner, '/api/medication-catalog', values)
        assert response.status_code in (400, 422), response.text
    saved = catalog_drug(owner, brand_name='商品名')
    target = '/api/medication-catalog/' + saved['medication_id']
    for value in (None, '', '\t\u3000'):
        response = owner.patch(target, json={'generic_name': value})
        assert response.status_code in (400, 422), response.text
        assert owner.get(target).json()['generic_name'] == '目录药品'
    assert owner.patch(target, json={'brand_name': None}).status_code == 200
    assert owner.patch(target, json={'notes': '省略通用名时保留'}).status_code == 200
    from backend.app.plugins.medication.tools.parameters import create_parameters
    from backend.app.schemas.medication import Medication
    schema = create_parameters('medication', Medication)
    assert 'generic_name' in schema['required']
    assert schema['properties']['generic_name']['type'] == 'string'
