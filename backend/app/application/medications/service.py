"""Authorized medication capabilities shared by HTTP and the agent."""


from contextlib import contextmanager, nullcontext

from backend.app.core.errors import raise_error
from backend.app.core.business_operation import validate_operation_id
from backend.app.repositories.members.repository import MemberRepository
from backend.app.repositories.medication_repository import MedicationRepository
from backend.app.schemas.medication import calendar, MODELS


class MedicationService:
    def __init__(self, members=None, *, notifications=None):
        from backend.app.application.notifications.service import NotificationService
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
        operation_id=None,
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
            if creating:
                validate_operation_id(operation_id)
            if uploads is not None and (
                kind != 'medication' or not creating or not isinstance(uploads, list)
            ):
                raise ValueError('原件列表只能随创建药品提交。')
            sources = self.normalize_sources(uploads, operation_id) if uploads else []
            return repo.save(actor, member, kind, changes, object_id=object_id,
                             operation_id=operation_id, medication_id=medication_id, sources=sources)

    def delete(self, actor, member, kind, object_id, *, medication_id=None):
        if kind == 'medication' and member is not None:
            raise_error('forbidden', 'MEDICATION_CATALOG_SETTINGS_ONLY', '药品基本信息只能在设置中维护。')
        with self.repository(actor, member, write=True) as repo:
            return repo.delete(actor, member, kind, object_id, medication_id=medication_id)

    def source(self, actor, member, medication_id, resource_id):
        from backend.app.repositories.medication_source_repository import MedicationSourceRepository
        with self.repository(actor, member) as repo:
            return MedicationSourceRepository(repo).read(member, medication_id, resource_id)

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

    def normalize_sources(self, sources, operation_id):
        import hashlib
        from uuid import uuid4
        from backend.app.application.medications.file_validation import validate_medication_file
        if not isinstance(sources, list) or not 1 <= len(sources) <= 20:
            raise_error('invalid_input', 'MEDICATION_ARGUMENTS_INVALID', '每次须提交 1 至 20 个药品来源。')
        normalized = []
        total = 0
        for source in sources:
            value = dict(source)
            value['resource_id'] = str(uuid4())
            content = value['content']
            value['mime_type'] = validate_medication_file(value['mime_type'], content, value['purpose'], operation_id)
            value['sha256'] = hashlib.sha256(content).hexdigest()
            total += len(content)
            normalized.append(value)
        if total > 100 * 1024 * 1024:
            raise_error('resource_limit', 'MEDICATION_SOURCES_TOO_LARGE', '本次药品原件总大小不能超过 100 MB。')
        return normalized

    def add_sources(self, actor, member, medication_id, uploads, operation_id):
        normalized = self.normalize_sources(uploads, operation_id)
        with self.repository(actor, member, write=True) as repo:
            if repo.account_id != actor:
                raise_error('forbidden', 'MEDICATION_CATALOG_OWNER_REQUIRED', '补充药品原件需要健康档案所有者账号权限。')
            return repo.add_sources(actor, member, medication_id, normalized, operation_id=operation_id)

    def drain_files(self, owner):
        from backend.app.repositories.medication_source_repository import MedicationSourceRepository
        return MedicationSourceRepository(MedicationRepository(owner, self.members.paths)).drain_files()
