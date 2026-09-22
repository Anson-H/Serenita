"""Read committed business changes and receive authorized evidence reliably."""

from backend.app.domain.memory.sources import SOURCE_REGISTRATIONS, BUSINESS_SOURCE_DATABASES
from backend.app.core.errors import SerenitaError
from backend.app.domain.memory.change_scope import memory_change_fields
from backend.app.schemas.memory.append import stable_memory_id


class MemoryBusinessSources:
    def __init__(self, memory):
        self.memory, self.members = memory, memory.members
        self.repository = MemoryBusinessSourceRepository(memory.repository)
        self.sources = self.repository.sources


    def catalog(self, actor, member, database, *, after_sequence=0, limit=50):
        if database not in BUSINESS_SOURCE_DATABASES or type(after_sequence) is not int or after_sequence < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise SerenitaError("invalid_input", "MEMORY_DELIVERY_RANGE_INVALID", "请选择已登记的业务库和有效记录范围。")
        with self.members.access_guard(actor, member) as access:
            setting = self.memory.repository.settings(actor, member) or {}
            categories = setting.get('source_categories', [])
            if setting.get('formation_state') != 'enabled' or not categories:
                return {"changes": [], "next_sequence": None, "gaps": ["该资料范围尚未开启自动接收。"]}
            try:
                rows, eligible = self.repository.pending_changes(access.account_id, member, database, after_sequence, limit)
            except FileNotFoundError:
                rows = []
            changes, gaps = [], []
            for row in rows[:limit]:
                if row['change_id'] not in eligible:
                    continue
                registration = SOURCE_REGISTRATIONS.get(row["resource_type"])
                if registration is None or registration.database != database:
                    gaps.append({"change_sequence": row["change_sequence"], "reason": "业务来源尚未登记。"})
                    continue
                category = next(iter(registration.categories))
                try:
                    self.memory.repository.evidence.check_changes(actor, member,
                        [{'source_database': database, 'change_id': row['change_id']}])
                except SerenitaError as error:
                    if error.kind in {'missing', 'forbidden'}:
                        continue
                    raise
                attempt = self.repository.find_processing(actor, member, database, row["change_id"])
                changes.append({"change_id": row["change_id"], "change_sequence": row["change_sequence"],
                                "operation_kind": row["operation_kind"], "source_category": category,
                                "delivery_status": "received" if attempt else "pending", "processing_attempt": attempt})
            return {"changes": changes, "next_sequence": rows[limit - 1]["change_sequence"] if len(rows) > limit else None, "gaps": gaps}


    def receive(self, actor, member, database, change_id):
        """Receive the reference, check access, find a task, then register or reuse it."""
        from backend.app.application.memory.sources.reception import MemoryReceptionRecorder
        # Resolve the owning account before storing any member-scoped receipt.
        with self.members.access_guard(actor, member) as access:
            recorder = MemoryReceptionRecorder(self.memory.paths, access, database, change_id)
            request = {'actor_account_id': actor, 'member_id': member, 'source_database': database,
                       'change_id': change_id}
            with recorder.step('received', request) as trace:
                trace['output'] = {'source_database': database, 'change_id': change_id, 'member_id': member}
            with recorder.step('registered', request) as registration:
                with recorder.step('permission_check', request, 'registered') as trace:
                    with self.members.access_guard(actor, member, write=True) as access:
                        trace['output'] = {'member_write_allowed': True}
                        change = self.memory.repository.evidence.read_changes(actor, member,
                            [{'source_database': database, 'change_id': change_id}])[0]
                        trace['output']['source_read_allowed'] = True
                        fields=memory_change_fields(change['resource_type'],change['fields'])
                        if not fields:
                            raise SerenitaError('forbidden','MEMORY_ATTACHMENT_CHANGE_EXCLUDED','该变更不属于记忆提取范围。')
                        setting=self.memory.repository.settings(actor,member) or {}
                        trace['output'].update(content_eligible=True,
                            formation_state=setting.get('formation_state'),
                            enabled_at=setting.get('effective_at'),
                            source_category=change['source_category'],
                            source_category_allowed=change['source_category'] in setting.get('source_categories', []),
                            recorded_at=change['recorded_at'])
                        if setting.get('formation_state') != 'enabled':
                            code = 'MEMORY_FORMATION_PAUSED' if setting.get('formation_state') == 'paused' else 'MEMORY_FORMATION_DISABLED'
                            raise SerenitaError('forbidden', code, '当前范围的自动记忆形成已暂停或尚未开启。')
                        if change['memory_status'] in {'not_included', 'skipped'}:
                            raise SerenitaError('forbidden','MEMORY_SOURCE_OUTSIDE_RECEPTION_SCOPE','该变更不在最近一次开启后的记忆接收范围内。')
                    trace['output']['allowed'] = True
                with recorder.step('registration_check', {'source_database':database,'change_id':change_id,'member_id':member}, 'registered') as trace:
                    attempt=self.repository.find_processing(actor,member,database,change_id)
                    trace['output']={'processing_attempt':attempt}
                with recorder.step('registration_save', {'source_database':database,'change_id':change_id,'member_id':member,'existing_attempt_id':attempt['attempt_id'] if attempt else None}, 'registered') as trace:
                    reused=attempt is not None
                    if attempt is None:
                        operation=stable_memory_id(member,'change-processing','event_formation',database+'/'+change_id)
                        attempt_id=stable_memory_id(member,operation,'processing_attempt','attempt')
                        batch={'attempts':[{
                            'attempt_id':attempt_id,'source_account_id':access.account_id,'source_database':database,
                            'change_id':change_id,'change_sequence':change['change_sequence'],'task_kind':'event_formation',
                            'purpose':'读取业务变更并提取事件与实体；逐个事件筛选一个事项，读取其全部事件后联合判断并保存归属与关系，不合适则创建独立事项；追加完整事项版本后处理下一个事件。',
                            'input_sequence':self.memory.repository.snapshot(actor,member)['record_cutoff'],
                            'coverage':[]}], 'attempt_updates':[{'attempt_id': attempt_id, 'processing_status': 'pending'}]}
                        trace['input']['save_command']={'operation_id':operation,'batch':batch}
                        saved=self.memory.repository.write(actor,member,operation,batch,command={'source_database':database,'change_id':change_id},return_attempts=True)
                        attempt=saved.pop('attempts')[0]
                        trace['output']={'commit':saved}
                    trace.setdefault('output',{}).update(reused=reused,processing_attempt=attempt)
                result={'status':'received','source_database':database,'change_id':change_id,'processing_attempt':attempt}
                registration['output']=result
                return result

from backend.app.repositories.memory.sources.business_sources import MemoryBusinessSourceRepository
