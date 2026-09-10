from uuid import uuid4
from datetime import datetime, timezone, timedelta
import pytest
from member_support import accounts, account_id, create_member, grant, report_payload
from backend.app.application.services import ApplicationServices
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect


def url(member,kind='medications',key=None): return f'/api/members/{member}/{kind}'+(f'/{key}' if key else '')
def post(client,path,payload,key=None): return client.post(path,json=payload,headers={'Idempotency-Key':key or str(uuid4())})
def plan_values(**changes): return {'starts_at':'2026-09-01T00:00:00+08:00','start_precision':'date','timezone':'Asia/Shanghai','dose_text':'1 片','schedule':{'kind':'daily','times':[{'time':'08:00'}]},**changes}

def add_original(service, actor, member, medication_id, filename, mime, content, purpose='package', request_id=None):
    return service.add_sources(actor, member, medication_id, [{'original_filename': filename,
        'mime_type': mime, 'content': content, 'purpose': purpose}], request_id)


def execute_medication_tool(tool, arguments, *, text='药品资料', visible=None, observations=()):
    from backend.app.agent_runtime.context import AgentContext
    from backend.app.agent_runtime.tools.parameters import validate_parameters
    context = AgentContext(account_id=tool.context.account_id, member_id=tool.context.member_id,
        task_type='conversation', session_id='session', input_text=text,
        memory={'current_message_id': 'message', 'visible_attachments': visible or {}})
    validate_parameters(arguments, tool.input_schema_for_context(context), label='药品工具')
    return tool.run(tool.bind_runtime_arguments(arguments, context=context, observations=list(observations)))


def plan_input(value, exclude=frozenset()):
    from backend.app.schemas.medication import Plan
    return {key: value[key] for key in Plan.model_fields if key in value and key not in exclude}

def drug(client,member):
    r=post(client,'/api/medication-catalog',{'generic_name':'测试药品','strength':'5 mg'})
    assert r.status_code==201,r.text
    return r.json()


def plan(client,member,medication=None,values=None):
    medication = medication or drug(client,member)
    r=post(client,url(member,'medication-plans'),{'medication_id':medication['medication_id'],**(values or plan_values())})
    assert r.status_code==201,r.text
    return r.json()










def test_plan_requires_start_dates_and_rejects_clearing_them(accounts):
    owner,*_=accounts; member=create_member(owner)
    target=url(member,'medication-plans'); med=drug(owner,member)
    for start in ({}, {'starts_at':None,'start_precision':None}):
        response=post(owner,target,{'medication_id':med['medication_id'],**start})
        assert response.status_code==400,response.text
        assert 'starts_at' in response.text
    assert owner.get(target).json()['items']==[]
    saved=plan(owner,member,values=plan_values(schedule={'kind':'as_needed'}))
    assert saved['ends_at'] is None
    detail=url(member,'medication-plans',saved['medication_plan_id'])
    invalid={**plan_input(saved),'starts_at':None,'start_precision':None}
    assert owner.patch(detail,json={**invalid}).status_code==400
    assert owner.patch(detail,json={'phases':[saved,{'phase_id':str(uuid4())}]}).status_code==400
    assert owner.get(detail).json()==saved




def test_plan_tool_rejects_manual_identity_and_reads_medicine_box(accounts):
    from backend.app.plugins.medication.registry import build_tools
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    from backend.app.core.errors import SerenitaError
    owner,*_=accounts; member=create_member(owner); med=drug(owner,member)
    tools={t.name:t for t in build_tools(runtime_context=PluginRuntimeContext(account_id=account_id('owner'),member_id=member,event_recorder=lambda _:None))}
    create=tools['create_medication_plan']; payload={'request_id':str(uuid4()),**plan_values()}
    with pytest.raises(SerenitaError): create.run({**payload,'medication_identity':{'generic_name':'手填'}})
    with pytest.raises(SerenitaError): create.run(payload)
    result=create.run({**payload,'medication_id':med['medication_id']}).output
    assert result['medication_identity']['generic_name']==med['generic_name']
    assert 'path' not in result
    with pytest.raises(SerenitaError):
        tools['update_medication_plan'].run({'medication_plan_id':result['medication_plan_id'],'medication_identity':{'generic_name':'手填'}})


def test_plan_query_returns_full_plans_with_filters_and_pagination(accounts):
    from backend.app.plugins.medication.registry import build_tools
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    from backend.app.core.errors import SerenitaError

    owner, *_ = accounts
    member = create_member(owner)
    med = drug(owner, member)
    saved = [plan(owner, member, med, values=plan_values(
        usage_status='taking', route='口服', notes='已确认安排',
        ends_at='2026-09-08T00:00:00+08:00', end_precision='date',
    )) for _ in range(25)]
    plan(owner, member, med, values=plan_values(usage_status='paused', schedule=None))
    plan(owner, create_member(owner), med)
    tools = {tool.name: tool for tool in build_tools(runtime_context=PluginRuntimeContext(
        account_id=account_id('owner'), member_id=member, event_recorder=lambda _: None))}
    assert 'read_medication_plan_catalog' not in tools
    read = tools['read_medication_plan']
    assert execute_medication_tool(read, {}).output['total'] == 26
    filters = {'query': med['generic_name'], 'status': 'taking',
               'after_date': '2026-09-07', 'before_date': '2026-09-07'}
    first = execute_medication_tool(read, filters)
    second = first.next_page()
    assert first.output['total'] == second.output['total'] == 25
    assert second.next_page is None
    assert second.output['pagination'] == {'page': 2, 'complete': True}
    returned = first.output['items'] + second.output['items']
    assert {item['medication_plan_id'] for item in returned} == {item['medication_plan_id'] for item in saved}
    for result in (first, second):
        for item in result.output['items']:
            expected = next(value for value in saved if value['medication_plan_id'] == item['medication_plan_id'])
            assert item == expected
            assert 'path' not in item
        assert {ref['resource_id'] for ref in result.effects['resource_refs']} == {item['medication_plan_id'] for item in result.output['items']}
    target = {'medication_plan_id': saved[0]['medication_plan_id']}
    assert execute_medication_tool(read, target).output == {
        'items': [saved[0]], 'total': 1, 'pagination': {'page': 1, 'complete': True},
    }
    empty = execute_medication_tool(read, {**target, 'status': 'paused'})
    assert empty.output == {'items': [], 'total': 0, 'pagination': {'page': 1, 'complete': True}}
    assert empty.effects['resource_refs'] == []
    assert execute_medication_tool(read, {**target, 'after_date': '2026-09-08'}).output['items'] == []
    with pytest.raises(ValueError):
        execute_medication_tool(read, {**filters, **target, 'cursor': 'not-model-input'})
    updated = execute_medication_tool(tools['update_medication_plan'], {**target, 'notes': '已修正'})
    assert 'path' not in updated.output
    assert execute_medication_tool(read, target).output['items'] == [updated.output]


def test_plan_query_rejects_invalid_foreign_and_deleted_identifiers(accounts):
    from backend.app.plugins.medication.registry import build_tools
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    from backend.app.core.errors import SerenitaError

    owner, reader, _ = accounts
    member = create_member(owner)
    saved = plan(owner, member)
    other_plan = plan(owner, create_member(owner))
    foreign_plan = plan(reader, create_member(reader))
    read = next(tool for tool in build_tools(runtime_context=PluginRuntimeContext(
        account_id=account_id('owner'), member_id=member, event_recorder=lambda _: None))
        if tool.name == 'read_medication_plan')
    for invalid in (None, '', '  ', 1):
        with pytest.raises(SerenitaError):
            read.run({'medication_plan_id': invalid})
    for invalid in (other_plan['medication_plan_id'], foreign_plan['medication_plan_id'], 'missing'):
        with pytest.raises(SerenitaError) as exc:
            execute_medication_tool(read, {'medication_plan_id': invalid})
        assert exc.value.kind == 'missing'
    assert owner.delete(url(member, 'medication-plans', saved['medication_plan_id'])).status_code == 200
    with pytest.raises(SerenitaError) as exc:
        execute_medication_tool(read, {'medication_plan_id': saved['medication_plan_id']})
    assert exc.value.kind == 'missing'
    assert execute_medication_tool(read, {}).output['items'] == []


def test_plan_notes_are_the_only_supplementary_text(accounts):
    from backend.app.plugins.medication.registry import build_tools
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    from backend.app.core.errors import SerenitaError

    owner,*_=accounts; member=create_member(owner); med=drug(owner,member)
    tools={t.name:t for t in build_tools(runtime_context=PluginRuntimeContext(account_id=account_id('owner'),member_id=member,event_recorder=lambda _:None))}
    payload={'medication_id':med['medication_id'],**plan_values(),'notes':'按复诊医嘱使用。'}
    target=url(member,'medication-plans')
    assert post(owner,target,{**payload,'reason':'重复说明'}).status_code==400
    saved=post(owner,target,payload).json()
    detail=url(member,'medication-plans',saved['medication_plan_id'])
    assert saved['notes']==payload['notes'] and 'reason' not in saved
    assert owner.patch(detail,json={'reason':None}).status_code==400
    assert owner.get(detail).json()==saved
    for name in ('create_medication_plan','update_medication_plan'):
        assert 'reason' not in tools[name].input_schema['properties']
    with pytest.raises(SerenitaError):
        tools['update_medication_plan'].run({'medication_plan_id':saved['medication_plan_id'],'reason':'重复说明'})
    assert tools['update_medication_plan'].run({'medication_plan_id':saved['medication_plan_id'],'notes':'按用户确认的医嘱使用。'}).output['notes']=='按用户确认的医嘱使用。'
    with connect(app_paths().medications_db(account_id('owner'))) as db:
        for table,removed in {
            'medication_plans':{'reason','medication_identity'},
            'medication_source_cleanup_outbox':{'member_id','attempt_count'},
        }.items():
            columns={r[1] for r in db.execute(f'PRAGMA table_info({table})')}
            assert not columns & removed
            assert 'created_at' in columns
            if table!='medication_source_cleanup_outbox': assert 'updated_at' in columns


def test_plan_permissions_and_member_delete(accounts):
    owner,reader,editor=accounts; member=create_member(owner); other=create_member(owner)
    grant(owner,member,'reader','read'); grant(owner,member,'editor','edit')
    med=drug(owner,member); p=plan(owner,member,med); target=url(member,'medication-plans',p['medication_plan_id'])
    original=plan_input(p); later=plan_values(starts_at='2026-09-07T12:00:00+08:00',start_precision='minute')
    assert owner.patch(target,json={'phases':[original,later]}).status_code==400
    assert owner.get(target).json()==p
    assert owner.patch(target,json={'phases':[{**original,'ends_at':later['starts_at'],'end_precision':'minute'},later]}).status_code==400
    assert owner.get(target).json()==p
    updated=owner.patch(target,json={**{**original,'ends_at':later['starts_at'],'end_precision':'minute'}})
    assert updated.status_code==200,updated.text
    assert reader.patch(target,json={'notes':'禁止'}).status_code==403
    assert editor.patch(target,json={'notes':'可以'}).status_code==200
    assert owner.get(url(other,'medication-plans',p['medication_plan_id'])).status_code==404
    assert owner.delete(f'/api/members/{member}').status_code==200
    with connect(app_paths().medications_db(account_id('owner'))) as db:
        assert db.execute('SELECT count(*) FROM medications').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM medication_plans').fetchone()[0]==0



def test_same_medicine_has_independent_plans_with_one_arrangement_each(accounts):
    owner,*_=accounts; member=create_member(owner); med=drug(owner,member)
    first=plan(owner,member,med,values=plan_values(ends_at='2026-09-08T00:00:00+08:00',end_precision='date'))
    second=plan(owner,member,med,values=plan_values(starts_at='2026-09-08T00:00:00+08:00',dose_text='2 片'))
    assert first['medication_plan_id']!=second['medication_plan_id']
    rows=owner.get(url(member,'medication-plans')).json()['items']
    assert len(rows)==2 and all(row['medication_id']==med['medication_id'] and 'phases' not in row and 'phase_id' not in row for row in rows)
    assert post(owner,url(member,'medication-plans'),{'medication_id':med['medication_id'],'phases':[plan_input(first),plan_input(second)]}).status_code==400
    assert owner.patch(url(member,'medication-plans',first['medication_plan_id']),json={**{**plan_input(first),'dose_text':'1 片'}}).status_code==200
    assert owner.get(url(member,'medication-plans',second['medication_plan_id'])).json()==second
    owner.delete(url(member,'medication-plans',first['medication_plan_id']))
    assert owner.get(url(member,'medication-plans',second['medication_plan_id'])).json()==second









def test_schedule_dst_and_frequency():
    from backend.app.domain.medication_schedule import local_instant,occurrences
    from backend.app.schemas.medication import Plan,Schedule
    from datetime import date
    from zoneinfo import ZoneInfo
    zone=ZoneInfo('America/New_York')
    assert local_instant(date(2026,3,8),'02:30',zone).astimezone(zone).strftime('%H:%M')=='03:00'
    assert local_instant(date(2026,11,1),'01:30',zone).astimezone(zone).fold==0
    for invalid in ({'kind':'daily','times':[{'time':'08:00'}],'times_per_day':2},{'kind':'weekly','weekdays':[1,1]},{'kind':'as_needed','times':[{'time':'08:00'}]}):
        with pytest.raises(ValueError): Schedule.model_validate(invalid)
    p=Plan.model_validate(plan_values(medication_id="drug",schedule={'kind':'every_n_days','interval_days':2,'anchor_date':'2026-09-01','times':[{'time':'08:00'}]})).model_dump()
    assert len(occurrences(p,datetime.fromisoformat('2026-09-01T00:00:00+08:00'),datetime.fromisoformat('2026-09-06T00:00:00+08:00')))==3
    for removed in ('every_n_hours','free_text'):
        with pytest.raises(ValueError): Schedule.model_validate({'kind':removed})


def test_decimal_pagination_intervals_and_atomic_failure(accounts):
    import sqlite3
    from backend.app.application.medication_service import MedicationService
    owner,*_=accounts; member=create_member(owner); actor=account_id('owner')
    med=drug(owner,member); base=url(member,key=med['medication_id'])
    precise='123456789012345678901234567890.1234567890123456789'
    assert post(owner,base+'/batches',{'quantity':precise}).json()['quantity']==precise
    p=plan(owner,member,med); before=owner.get(url(member,'medication-plans',p['medication_plan_id'])).json()
    second=plan_values(starts_at='2026-09-08T00:00:00+08:00',start_precision='date',schedule=None,usage_status='paused')
    with connect(app_paths().medications_db(actor)) as db:
        db.execute("CREATE TRIGGER fail_plan BEFORE UPDATE ON medication_plans BEGIN SELECT RAISE(ABORT,'injected failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        MedicationService().save(actor,member,'plan',{**second},object_id=p['medication_plan_id'])
    assert owner.get(url(member,'medication-plans',p['medication_plan_id'])).json()==before
    with connect(app_paths().medications_db(actor)) as db: db.execute('DROP TRIGGER fail_plan')
    another=drug(owner,member)
    first=owner.get(url(member)+'?limit=1').json()
    assert first['total']==2
    assert first['items'][0]['medication_id']==another['medication_id']
    second_page=owner.get(url(member),params={'limit':1,'cursor':first['next_cursor']}).json()
    assert second_page['items'][0]['medication_id']==med['medication_id']
    assert second_page['next_cursor'] is None
    assert second_page['total']==2
    assert owner.get(url(member),params={'query':'does-not-exist'}).json()['total']==0
    assert owner.get(url(member),params={'cursor':first['next_cursor'],'query':'different'}).status_code==400
    assert owner.get(url(member,'medication-plans'),params={'after_date':'2026-09-08','before_date':'2026-09-08'}).json()['items'][0]['medication_plan_id']==p['medication_plan_id']


def test_catalog_totals_match_member_filters_and_ignore_pagination(accounts):
    owner,*_=accounts; member=create_member(owner); other=create_member(owner)
    med=drug(owner,member)
    plan(owner,member,med)
    plan(owner,member,med)
    plan(owner,member,med,values=plan_values(starts_at='2030-01-01T00:00:00+08:00'))
    plan(owner,other)
    filters={'before_date':'2026-09-02','limit':1}
    first=owner.get(url(member,'medication-plans'),params=filters).json()
    assert first['total']==2 and len(first['items'])==1 and first['next_cursor']
    second=owner.get(url(member,'medication-plans'),params={**filters,'cursor':first['next_cursor']}).json()
    assert second['total']==2 and len(second['items'])==1 and second['next_cursor'] is None
    assert owner.get(url(member,'medication-plans'),params={'query':'does-not-exist'}).json()['total']==0
    assert owner.get(url(member,'medication-plans')).json()['total']==3
    assert owner.get(url(other,'medication-plans')).json()['total']==1
    assert owner.get(url(member)).json()['total']==2






def test_medication_harness_observes_failure_and_corrects(accounts):
    from backend.app.plugins.medication.registry import build_tools,build_skills
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    from backend.app.agent_runtime.context import AgentContext
    from backend.app.agent_runtime.model_types import AssistantModelOutput
    from tests.agent_support import HarnessDriver,call,runtime
    owner,*_=accounts; member=create_member(owner); actor=account_id('owner')
    from backend.app.plugins.registry import build_available_tools
    tools=build_available_tools(runtime_context=PluginRuntimeContext(account_id=actor,member_id=member,event_recorder=lambda _:None))
    med=drug(owner,member)
    driver=HarnessDriver(call('skill','load_skill',name='medication-plan'),call('bad','create_medication_plan',request_id='bad',medication_id=med['medication_id'],starts_at=None),call('correct','create_medication_plan',request_id='correct',medication_id=med['medication_id'],**plan_values(schedule=None)),AssistantModelOutput(content='已按提供的开始日期记录。'))
    result=runtime(skills=build_skills(),tools=tools).execute(AgentContext(account_id=actor,member_id=member,task_type='conversation',input_text='请保存测试药品的用药计划，2026年9月1日开始'),derive_messages=driver.derive,complete_model=driver.complete,on_event=driver.record)
    assert any(e.type=='tool_error' for e in result.events)
    rows=owner.get(url(member,'medication-plans')).json()['items']
    assert len(rows)==1 and rows[0]['starts_at']=='2026-09-01T00:00:00+08:00', [(e.type,e.payload) for e in result.events if e.type=='tool_error']
    assert len(driver.requests)==4
    assert any(m.get('role')=='tool' and m.get('name')=='create_medication_plan' for m in driver.requests[2].messages)


def test_medication_capabilities_are_box_plans_batches_and_reminders(accounts):
    from backend.app.plugins.medication.registry import build_tools
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    from backend.app.schemas.medication import MODELS
    owner,*_=accounts; member=create_member(owner); drug(owner,member)
    assert set(MODELS)=={'medication','plan','batch'}
    tools=build_tools(runtime_context=PluginRuntimeContext(account_id=account_id('owner'),member_id=member,event_recorder=lambda _:None))
    assert not any('medication_record' in t.name for t in tools)
    assert owner.get(url(member,'medication-records')).status_code==404
    assert post(owner,url(member,'medication-records'),{'outcome':'taken'}).status_code==404
    for action in ('taken','skipped'):
        assert owner.post('/api/notifications/unsupported/actions',json={'action':action}).status_code==422
    with connect(app_paths().medications_db(account_id('owner'))) as db:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not {'medication_records','medication_records_report_links'} & tables




def test_plan_fields_match_storage_and_tool_contract(accounts):
    from backend.app.plugins.medication.registry import build_tools
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    owner,*_=accounts; member=create_member(owner)
    saved=plan(owner,member); target=url(member,'medication-plans',saved['medication_plan_id'])
    removed={'phases','phase_id','timing_note','site','administration_note','change_reason'}
    for field in removed:
        invalid={**plan_input(saved),field:'不接受的内容'}
        assert owner.patch(target,json={**invalid}).status_code==400
    invalid={**plan_input(saved),'schedule':{**saved['schedule'],'instruction_text':'不接受的内容'}}
    assert owner.patch(target,json={**invalid}).status_code==400
    invalid={**plan_input(saved),'schedule':{'kind':'daily','times':[{'time':'08:00','dose_text':'2 片'}]}}
    assert owner.patch(target,json={**invalid}).status_code==400
    assert post(owner,url(member,'medication-plans'),{'medication_id':saved['medication_id'],**invalid}).status_code==400
    assert owner.get(target).json()==saved
    assert not removed.intersection(saved)
    assert 'instruction_text' not in saved['schedule']
    with connect(app_paths().medications_db(account_id('owner'))) as db:
        assert not removed.intersection(r[1] for r in db.execute('PRAGMA table_info(medication_plans)'))
    tools=build_tools(runtime_context=PluginRuntimeContext(account_id=account_id('owner'),member_id=member,event_recorder=lambda _:None))
    for tool in tools:
        if tool.name not in ('create_medication_plan','update_medication_plan'):continue
        props=tool.input_schema['properties']
        assert not removed.intersection(props)
        schedule=next(v for v in props['schedule']['anyOf'] if v.get('type')=='object')
        assert 'instruction_text' not in schedule['properties']
        assert set(schedule['properties']['times']['items']['properties']) == {'time'}


def test_all_scheduled_times_use_the_plan_dose(accounts):
    from backend.app.domain.medication_schedule import occurrences
    owner,*_=accounts; member=create_member(owner)
    saved=plan(owner,member,values=plan_values(dose_text='2 滴',schedule={'kind':'daily','times':[{'time':'08:00'},{'time':'20:00'}]}))
    p=saved
    assert p['schedule']['times']==[{'time':'08:00'},{'time':'20:00'}]
    bounds=[datetime.fromisoformat(v) for v in ('2026-09-01T00:00:00+08:00','2026-09-02T00:00:00+08:00')]
    assert [dose for _,dose in occurrences(p,*bounds)]==['2 滴','2 滴']
    with connect(app_paths().medications_db(account_id('owner'))) as db:
        import json
        row=db.execute('SELECT dose_text,schedule FROM medication_plans WHERE medication_plan_id=?',(saved['medication_plan_id'],)).fetchone()
        assert row['dose_text']=='2 滴'
        assert json.loads(row['schedule'])['times']==[{'time':'08:00'},{'time':'20:00'}]
    p={**p,'dose_text':None}
    assert [dose for _,dose in occurrences(p,*bounds)]==[None,None]




@pytest.mark.parametrize('ending', [None, 'long_term', '2026-09-10T00:00:00+08:00'])
def test_plan_end_choices_persist_and_drive_date_queries(accounts, ending):
    from backend.app.domain.medication_schedule import occurrences
    owner, *_ = accounts
    member = create_member(owner)
    precision = 'date' if ending and ending != 'long_term' else None
    saved = plan(owner, member, values=plan_values(ends_at=ending, end_precision=precision))
    detail = url(member, 'medication-plans', saved['medication_plan_id'])
    stored = owner.get(detail).json()
    assert stored['ends_at'] == ending
    assert stored['end_precision'] == precision
    results = owner.get(url(member, 'medication-plans'), params={'after_date': '2026-09-11'}).json()['items']
    assert bool(results) == (precision is None)
    due = occurrences(stored, datetime(2026, 9, 11, tzinfo=timezone.utc), datetime(2026, 9, 12, tzinfo=timezone.utc))
    assert bool(due) == (precision is None)
    for next_end in ('long_term', None):
        response = owner.patch(detail, json={**{**plan_input(stored), 'ends_at': next_end, 'end_precision': None}})
        assert response.status_code == 200, response.text
        assert owner.get(detail).json()['ends_at'] == next_end
    invalid = owner.patch(detail, json={**{**plan_input(stored), 'ends_at': 'long_term', 'end_precision': 'date'}})
    assert invalid.status_code == 400
    assert owner.get(detail).json()['ends_at'] is None








def test_catalog_and_notification_reads_use_bounded_projections(accounts,monkeypatch):
    import json
    from contextlib import contextmanager
    import backend.app.repositories.medication_repository as storage
    from backend.app.repositories.medication_repository import MedicationRepository
    from backend.app.repositories.report_repository import ReportRepository
    owner,*_=accounts;member=create_member(owner);actor=account_id('owner')
    med=drug(owner,member)
    service=ApplicationServices();repo=MedicationRepository(actor,app_paths())
    with repo.transaction(True) as db:
        for n in range(199):
            row=dict(db.execute('SELECT * FROM medication_data.medications WHERE medication_id=?',(med['medication_id'],)).fetchone())
            row['medication_id']=str(uuid4());row['generic_name']=f'目录性能数据 {n}'
            repo.insert(db,'medications',row)
    plans = [plan(owner, member, med) for _ in range(30)]
    notifications = service.notifications
    notifications.set_preferences(actor, True)
    from backend.app.application.medication_notifications import MedicationNotificationProducer
    producer = MedicationNotificationProducer(notifications)
    for saved in plans:
        producer.publish(actor, member, saved, datetime.now(timezone.utc))
    queries=[];original=storage.connect
    @contextmanager
    def tracked(*args,**kw):
        with original(*args,**kw) as db:
            db.set_trace_callback(lambda sql:queries.append(sql) if sql.lstrip().upper().startswith('SELECT') else None)
            yield db
    monkeypatch.setattr(storage,'connect',tracked)
    monkeypatch.setattr(MedicationRepository,'detail',lambda *args,**kw:pytest.fail('catalog/inbox assembled a full detail'))
    monkeypatch.setattr(ReportRepository,'init_db',lambda *args:pytest.fail('catalog/inbox opened the report store'))
    page=service.medications.catalog(actor,member,'medication',limit=24)
    assert len(page['items'])==24 and page['next_cursor'] and page['total']==200
    assert all('files' not in item and 'batches' not in item for item in page['items'])
    catalog_queries=len(queries);assert catalog_queries==2
    queries.clear();inbox=notifications.list(actor)['items']
    assert len(inbox)==30
    assert len(queries)<=4
    print(json.dumps({'medication_catalog':{'input_rows':200,'page_rows':24,'select_queries':catalog_queries,'response_bytes':len(json.dumps(page,ensure_ascii=False).encode())},'notifications':{'visible':len(inbox),'member_store_select_queries':len(queries),'response_bytes':len(json.dumps(inbox,ensure_ascii=False).encode())}}))


def test_flat_plan_preserves_recorded_status_and_partial_updates(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    saved = plan(owner, member, values=plan_values(
        starts_at='2020-01-01T00:00:00+08:00', ends_at='2020-02-01T00:00:00+08:00',
        end_precision='date', usage_status='paused', schedule=None,
    ))
    assert saved['time_status'] == 'ended' and saved['usage_status'] == 'paused'
    target = url(member, 'medication-plans', saved['medication_plan_id'])
    changed = owner.patch(target, json={'notes': '复查后再确认', 'dose_text': '2 片'}).json()
    assert changed['usage_status'] == 'paused' and changed['schedule'] is None
    assert changed['starts_at'] == saved['starts_at'] and changed['ends_at'] == saved['ends_at']
    assert changed['dose_text'] == '2 片'
    rows = owner.get(url(member, 'medication-plans'), params={'status':'paused'}).json()['items']
    assert len(rows) == 1 and rows[0]['usage_status'] == 'paused'
    assert not {'phases', 'phase_id'} & changed.keys()
    with connect(app_paths().medications_db(account_id('owner'))) as db:
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name='medication_plan_phases'").fetchone() is None
        columns = {row[1]: row for row in db.execute('PRAGMA table_info(medication_plans)')}
        assert all(columns[key][3] for key in ('starts_at', 'start_precision'))
        stored = db.execute('SELECT dose_text,usage_status FROM medication_plans WHERE medication_plan_id=?', (saved['medication_plan_id'],)).fetchone()
        assert tuple(stored) == ('2 片', 'paused')
