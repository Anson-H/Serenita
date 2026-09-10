"""Authorized medication capabilities shared by HTTP and the agent."""


from contextlib import contextmanager, nullcontext

from backend.app.core.errors import raise_error
from backend.app.repositories.member_repository import MemberRepository
from backend.app.core.values import digest
from backend.app.repositories.medication_repository import MedicationRepository
from backend.app.schemas.medication import calendar, MODELS


class MedicationService:
    def __init__(self, members=None, *, notifications=None):
        from backend.app.application.notification_service import NotificationService
        self.members = members or MemberRepository()
        self.notifications = notifications or NotificationService(self.members)

    @contextmanager
    def repository(self, actor, member, *, write=False):
        with self.members.access_guard(actor, member, write=write) if member is not None else nullcontext(None) as access:
            try:
                yield MedicationRepository(access.account_id if access else actor, self.members.paths)
            except LookupError as exc:
                raise_error("missing", "MEDICATION_NOT_FOUND", str(exc))
            except ValueError as exc:
                raise_error("invalid_input", "MEDICATION_ARGUMENTS_INVALID", str(exc))
        if write and member is not None:
            self.notifications.resources_changed(member_id=member)

    def read(self, actor, member, kind, object_id):
        with self.repository(actor, member) as repo:
            return repo.read(member, kind, object_id)

    def catalog(self, actor, member, kind, **filters):
        with self.repository(actor, member) as repo:
            self.validate_catalog_filters(filters)
            if 'medication_plan_id' in filters:
                plan_id = filters['medication_plan_id']
                if kind != 'plan' or not isinstance(plan_id, str) or not plan_id.strip():
                    raise ValueError('用药计划标识必须为非空文字，且仅用于查询用药计划。')
            return repo.catalog(member, kind, filters)

    @staticmethod
    def validate_catalog_filters(filters):
        allowed = {
            "query",
            "status",
            "after_date",
            "before_date",
            "undated",
            "cursor",
            "limit",
            "medication_id",
            "medication_plan_id",
            "inventory_only",
        }
        if set(filters) - allowed:
            raise ValueError("未知筛选条件。")
        for key in ("after_date", "before_date"):
            if filters.get(key):
                calendar(filters[key])
        if (
            filters.get("after_date")
            and filters.get("before_date")
            and filters["after_date"] > filters["before_date"]
        ):
            raise ValueError("日期下界不能晚于上界。")
        limit = filters.get("limit", 24)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("每页数量须为 1 至 100。")

    def save(
        self,
        actor,
        member,
        kind,
        changes,
        object_id=None,
        request_id=None,
        medication_id=None,
        uploads=None,
    ):
        if kind == 'medication' and member is not None and object_id is not None:
            raise_error('forbidden', 'MEDICATION_CATALOG_SETTINGS_ONLY', '已有药品基本信息只能在设置中维护。')
        with self.repository(actor, member, write=True) as repo:
            if kind == 'medication' and repo.account_id != actor:
                raise_error('forbidden', 'MEDICATION_CATALOG_OWNER_REQUIRED', '向目录添加药品需要健康档案所有者账号权限。')
            model = MODELS[kind]
            if not changes:
                raise ValueError("至少提交一个可编辑字段。")
            unknown = set(changes) - model.model_fields.keys()
            if unknown:
                raise ValueError("未知字段：" + ",".join(sorted(unknown)))
            creating = object_id is None
            if uploads is not None and (
                kind != 'medication' or not creating or not isinstance(uploads, list)
            ):
                raise ValueError('原件列表只能随创建药品提交。')
            sources = self.normalize_sources(uploads, request_id) if uploads else []
            from backend.app.repositories.medication_source_repository import MedicationSourceRepository
            source_repo = MedicationSourceRepository(repo.account_id, repo.paths) if sources else None
            payload_hash = digest(
                {"kind": kind, "values": changes, "medication_id": medication_id,
                 **({'sources': [
                     {key: source[key] for key in ('original_filename', 'mime_type', 'sha256', 'purpose')}
                     for source in sources
                 ]} if kind == 'medication' and creating else {})}
            )
            with (source_repo.staging() if source_repo else nullcontext([])) as created, repo.transaction(True) as db:
                prior_id = repo.request_result(
                    db, actor=actor, member=member, request_id=request_id,
                    operation=kind, payload_hash=payload_hash,
                ) if creating else None
                if prior_id is not None:
                    object_id = prior_id
                    repo.detail(db, member, kind, object_id)
                else:
                    current = (
                        repo.detail(db, member, kind, object_id) if object_id else {}
                    )
                    merged = {
                        **{
                            key: value
                            for key, value in current.items()
                            if key in model.model_fields
                        },
                        **changes,
                    }
                    values = model.model_validate(merged).model_dump()
                    if kind == "plan":
                        repo.medication_identity(db, member, values["medication_id"])
                    if kind == "batch":
                        parent = medication_id if creating else current["medication_id"]
                        repo.medication_identity(db, member, parent)
                        values["medication_id"] = parent
                    if creating or any(
                        value != current.get(key) for key, value in values.items()
                    ):
                        object_id = repo.persist(
                            db,
                            member,
                            kind,
                            values,
                            object_id,
                        )
                    if creating:
                        if source_repo:
                            source_repo.link(db, member, object_id, sources, created, reject_duplicates=True)
                        repo.record_request(
                            db, actor=actor, member=member, request_id=request_id,
                            operation=kind, payload_hash=payload_hash, object_id=object_id,
                        )
            return repo.read(member, kind, object_id)

    def delete(self, actor, member, kind, object_id):
        if kind == 'medication' and member is not None:
            raise_error('forbidden', 'MEDICATION_CATALOG_SETTINGS_ONLY', '药品基本信息只能在设置中维护。')
        with self.repository(actor, member, write=True) as repo:
            return repo.delete(member, kind, object_id)

    def source(self, actor, member, medication_id, resource_id):
        from backend.app.repositories.medication_source_repository import MedicationSourceRepository
        with self.repository(actor, member) as repo:
            return MedicationSourceRepository(repo.account_id, repo.paths).read(member, medication_id, resource_id)

    def read_information(self, actor, member, medication_id=None, fields=None, **filters):
        with self.repository(actor, member) as repo:
            if set(filters) - {'query', 'cursor', 'limit'}:
                raise ValueError('未知药品信息筛选条件。')
            allowed = set(MODELS['medication'].model_fields) | {'sources', 'created_at', 'updated_at'}
            if fields is not None and (
                not isinstance(fields, list)
                or any(not isinstance(f, str) or f not in allowed for f in fields)
                or len(set(fields)) != len(fields)
            ):
                raise ValueError('药品信息读取字段无效。')
            if medication_id is not None:
                if not isinstance(medication_id, str) or not medication_id.strip():
                    raise ValueError('药品标识不能为空。')
                filters['medication_id'] = medication_id
            self.validate_catalog_filters(filters)
            selected = set(fields) if fields else allowed - {'sources'}
            selected |= {'generic_name', 'brand_name', 'strength', 'package_specification', 'created_at', 'updated_at'}
            return repo.catalog(member, 'medication', filters, medication_fields=selected)

    def read_inventory(self, actor, member, medication_id):
        with self.repository(actor, member) as repo:
            return repo.read_inventory(member, medication_id)

    def normalize_sources(self, sources, request_id):
        import hashlib
        from uuid import uuid4
        from backend.app.application.medication_file_validation import validate_medication_file
        if not isinstance(sources, list) or not 1 <= len(sources) <= 20:
            raise_error('invalid_input', 'MEDICATION_ARGUMENTS_INVALID', '每次须提交 1 至 20 个药品来源。')
        normalized = []
        total = 0
        for source in sources:
            value = dict(source)
            value['resource_id'] = str(uuid4())
            content = value['content']
            value['mime_type'] = validate_medication_file(value['mime_type'], content, value['purpose'], request_id)
            value['sha256'] = hashlib.sha256(content).hexdigest()
            total += len(content)
            normalized.append(value)
        if total > 100 * 1024 * 1024:
            raise_error('resource_limit', 'MEDICATION_SOURCES_TOO_LARGE', '本次药品原件总大小不能超过 100 MB。')
        return normalized

    def add_sources(self, actor, member, medication_id, uploads, request_id):
        from backend.app.repositories.medication_source_repository import MedicationSourceRepository
        normalized = self.normalize_sources(uploads, request_id)
        signature = digest({'medication_id': medication_id, 'uploads': [
            {k: s[k] for k in ('original_filename', 'mime_type', 'sha256', 'purpose')} for s in normalized]})
        with self.repository(actor, member, write=True) as repo:
            if repo.account_id != actor:
                raise_error('forbidden', 'MEDICATION_CATALOG_OWNER_REQUIRED', '补充药品原件需要健康档案所有者账号权限。')
            source_repo = MedicationSourceRepository(repo.account_id, repo.paths)
            with source_repo.staging() as created:
                with repo.transaction(True) as db:
                    prior = repo.request_result(db, actor=actor, member=member, request_id=request_id,
                        operation='sources', payload_hash=signature)
                    repo.detail(db, member, 'medication', medication_id)
                    if prior is None:
                        source_repo.link(db, member, medication_id, normalized, created, reject_duplicates=True)
                        repo.record_request(db, actor=actor, member=member, request_id=request_id,
                            operation='sources', payload_hash=signature, object_id=medication_id)
                    result = repo.detail(db, member, 'medication', medication_id)
            return result

    def drain_files(self, owner):
        from backend.app.repositories.medication_source_repository import MedicationSourceRepository
        return MedicationSourceRepository(owner, self.members.paths).drain_files()
