"""Report command transactions and precise business-field change capture."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
import hashlib
import inspect
import json
import re
from typing import Any

from backend.app.core.business_operation import current_business_operation
from backend.app.core.cancellation import tool_cancellation_scope
from backend.app.core.errors import raise_error
from backend.app.repositories.business_change_repository import record_change
from backend.app.repositories.business_operation_repository import begin_operation, finish_operation
from backend.app.schemas.report import REPORT_STRUCTURES
from backend.app.storage.sqlite import connect


def command_value(value):
    """Represent upload bytes by their exact digest; never persist their raw bytes."""
    if isinstance(value, (bytes, bytearray)):
        return {"sha256": hashlib.sha256(value).hexdigest(), "size_bytes": len(value)}
    if isinstance(value, dict):
        return {key: command_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [command_value(item) for item in value]
    if value is None or type(value) in (str, bool, int, float):
        return value
    # Repository iterable inputs are consumed once and passed on as lists.
    if hasattr(value, "__iter__"):
        return [command_value(item) for item in value]
    raise ValueError("医疗报告命令参数必须可表示为 JSON。")


def report_write(method):
    signature = inspect.signature(method)

    @wraps(method)
    def execute(self, *args, **kwargs):
        bound = signature.bind(self, *args, **kwargs)
        bound.apply_defaults()
        values = {key: value for key, value in bound.arguments.items() if key != "self"}
        for key, value in list(values.items()):
            if not isinstance(value, (dict, list, tuple, str, bytes, bytearray)) and value is not None and hasattr(value, "__iter__"):
                values[key] = list(value)
                bound.arguments[key] = values[key]
        command = {"domain": "medical_report", "action": method.__name__, "values": command_value(values)}

        def invoke():
            self._watch_report_write(method.__name__, values)
            return method(*bound.args, **bound.kwargs)
        return self.run_business_command(command, invoke)
    return execute


@dataclass
class ReportCommand:
    connection: Any
    actor: str
    operation: Any
    watched: dict = field(default_factory=dict)
    reserved_reports: set = field(default_factory=set)
    new_files: set = field(default_factory=set)
    catalog_before: dict | None = None


_COMMANDS: ContextVar[dict] = ContextVar("report_commands", default={})


def _pointer(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def report_snapshot(connection, member_id, report_id, *, schema_alias="main"):
    if not re.fullmatch(r"[a-z][a-z0-9_]*", schema_alias):
        raise ValueError("report database schema alias is invalid")
    prefix = f'"{schema_alias}".'
    row = connection.execute(f"SELECT * FROM {prefix}reports WHERE member_id=? AND report_id=?", (member_id, report_id)).fetchone()
    if row is None:
        return None
    fields = {"/" + key: row[key] for key in ("report_type", "report_name", "report_time", "institution_name", "analysis_content", "analysis_outdated", "analysis_updated_at")}
    if row["report_type"] == "检验报告":
        for item in connection.execute(f"SELECT * FROM {prefix}lab_test_report WHERE member_id=? AND report_id=?", (member_id, report_id)):
            for key in item.keys():
                if key not in {"report_id", "member_id", "item_id", "category_name"}:
                    fields[f"/lab_test_results/{_pointer(item['item_id'])}/{key}"] = item[key]
    else:
        table = REPORT_STRUCTURES[row["report_type"]][0]
        detail = connection.execute(f"SELECT * FROM {prefix}{table} WHERE member_id=? AND report_id=?", (member_id, report_id)).fetchone()
        if detail:
            fields.update({f"/{table}/{key}": detail[key] for key in detail.keys() if key not in {"report_id", "member_id"}})
    for source in connection.execute(f"SELECT resource_id,is_primary FROM {prefix}report_source_links WHERE member_id=? AND report_id=?", (member_id, report_id)):
        fields[f"/sources/{_pointer(source['resource_id'])}/is_primary"] = source["is_primary"]
    return fields


def source_snapshot(connection, member_id, resource_id, *, schema_alias="main"):
    if not re.fullmatch(r"[a-z][a-z0-9_]*", schema_alias):
        raise ValueError("report database schema alias is invalid")
    row = connection.execute(f'SELECT * FROM "{schema_alias}".report_sources WHERE member_id=? AND resource_id=?', (member_id, resource_id)).fetchone()
    return {"/" + key: row[key] for key in row.keys() if key not in {"member_id", "resource_id", "created_at"}} if row else None


def catalog_snapshot(connection):
    values = {}
    for item in connection.execute("SELECT * FROM lab_items"):
        fields = {"/" + key: json.loads(item[key]) if key == "aliases" else item[key] for key in item.keys() if key != "item_id"}
        for link in connection.execute("SELECT category_name,is_primary FROM lab_item_category_links WHERE item_id=?", (item["item_id"],)):
            fields[f"/categories/{_pointer(link['category_name'])}/is_primary"] = link["is_primary"]
        values[("lab_item", item["item_id"])] = fields
    for category in connection.execute("SELECT * FROM lab_categories"):
        values[("lab_category", category["category_name"])] = {"/category_name": category["category_name"], "/description": category["description"]}
    return values


class ReportChanges:
    @property
    def _command_key(self):
        return str(self.paths.reports_db(self.account_id).resolve())

    @property
    def active_business_command(self):
        return _COMMANDS.get().get(self._command_key)

    @contextmanager
    def connection(self):
        current = self.active_business_command
        if current is not None:
            yield current.connection
        else:
            with connect(self.paths.reports_db(self.account_id)) as connection:
                yield connection

    def reserve_report_id(self, report_id):
        current = self.active_business_command
        if current is not None:
            current.reserved_reports.add(report_id)

    def watch_report_on_connection(self, connection, member_id, report_id):
        current = self.active_business_command
        if current is None or current.connection is not connection:
            return
        key = ("report", member_id, report_id)
        if key not in current.watched:
            current.watched[key] = None if report_id in current.reserved_reports else report_snapshot(connection, member_id, report_id)
        for source in connection.execute("SELECT resource_id FROM report_source_links WHERE member_id=? AND report_id=?", (member_id, report_id)):
            self._watch_source(member_id, source["resource_id"])

    def _watch_source(self, member_id, resource_id):
        current = self.active_business_command
        key = ("report_source", member_id, resource_id)
        if key not in current.watched:
            current.watched[key] = source_snapshot(current.connection, member_id, resource_id)

    def _watch_report_write(self, action, values):
        current = self.active_business_command
        member_id = values.get("member_id")
        report_id = values.get("report_id")
        if member_id and report_id:
            self.watch_report_on_connection(current.connection, member_id, report_id)
        if member_id and values.get("resource_id"):
            self._watch_source(member_id, values["resource_id"])
            for row in current.connection.execute("SELECT report_id FROM report_source_links WHERE member_id=? AND resource_id=?", (member_id, values["resource_id"])):
                self.watch_report_on_connection(current.connection, member_id, row["report_id"])
        catalog_actions = {"create_lab_item", "update_lab_item", "merge_lab_items", "delete_lab_item", "create_lab_category", "update_lab_category", "delete_lab_category"}
        if action in catalog_actions or action in {"create_manual_report", "create_report_from_parsed", "merge_parsed_report", "reclassify_report"}:
            if current.catalog_before is None:
                current.catalog_before = catalog_snapshot(current.connection)
        if action in catalog_actions:
            # Capture only reports in the dictionary mutation's item/category scope.
            clauses, parameters = [], []
            for key in ("item_id", "source_item_id", "target_item_id"):
                if values.get(key):
                    clauses.append("l.item_id=?")
                    parameters.append(values[key])
            for key in ("category_name", "current_category_name", "primary_category_name"):
                if values.get(key):
                    clauses.append("l.category_name=?")
                    parameters.append(values[key])
            if clauses:
                for row in current.connection.execute("SELECT DISTINCT l.member_id,l.report_id FROM lab_test_report l WHERE " + " OR ".join(clauses), parameters):
                    self.watch_report_on_connection(current.connection, row["member_id"], row["report_id"])

    def run_business_command(self, command, perform, *, actor_account_id=None, drain_files=False):
        if self.active_business_command is not None:
            return perform()
        self.init_db()
        operation = current_business_operation()
        actor = actor_account_id or self.actor_account_id
        current = None
        try:
            with connect(self.paths.reports_db(self.account_id)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                from backend.app.repositories.memory.sources.source_deletions import bind_deletion_journal
                bind_deletion_journal(connection, self.paths, self.account_id, 'reports.db')
                old = begin_operation(connection, actor, operation.operation_id, command)
                if old is not None:
                    for kind, member_id, resource_id in old.get("required_resources", []):
                        snapshot = report_snapshot if kind == "report" else source_snapshot
                        if snapshot(connection, member_id, resource_id) is None:
                            raise_error("missing", "REPORT_SOURCE_NOT_FOUND" if kind == "report_source" else "REPORT_NOT_FOUND", "原命令引用的医疗报告或来源已不可用。")
                    return old["value"]
                current = ReportCommand(connection, actor, operation)
                token = _COMMANDS.set({**_COMMANDS.get(), self._command_key: current})
                try:
                    result = perform()
                    for report_id in current.reserved_reports:
                        row = connection.execute("SELECT member_id FROM reports WHERE report_id=?", (report_id,)).fetchone()
                        if row:
                            current.watched.setdefault(("report", row["member_id"], report_id), None)
                    required = []
                    for (kind, member_id, resource_id), before in current.watched.items():
                        snapshot = report_snapshot if kind == "report" else source_snapshot
                        after = snapshot(connection, member_id, resource_id)
                        context = {"member_id": member_id}
                        context.update({key.lstrip("/"): value for key, value in (after or before or {}).items() if key in {"/report_type", "/report_name", "/report_time", "/mime_type"}})
                        record_change(connection, actor_account_id=actor, operation_id=operation.operation_id,
                            scope_kind="member", member_id=member_id, resource_type=kind, resource_id=resource_id,
                            before=before, after=after, context=context, origin_kind=operation.origin_kind)
                        if after is not None:
                            required.append([kind, member_id, resource_id])
                    if current.catalog_before is not None:
                        after_catalog = catalog_snapshot(connection)
                        for kind, resource_id in sorted(current.catalog_before.keys() | after_catalog.keys()):
                            record_change(connection, actor_account_id=actor, operation_id=operation.operation_id,
                                scope_kind="account", member_id=None, resource_type=kind, resource_id=resource_id,
                                before=current.catalog_before.get((kind, resource_id)), after=after_catalog.get((kind, resource_id)),
                                context={"catalog": "lab_dictionary"}, origin_kind=operation.origin_kind)
                    finish_operation(connection, actor, operation.operation_id, {"value": command_value(result), "required_resources": required})
                finally:
                    _COMMANDS.reset(token)
            # Physical deletion follows the committed SQL transaction.
            if drain_files:
                with tool_cancellation_scope(None):
                    self.drain_file_cleanup()
            return result
        except Exception:
            if current and current.new_files:
                with tool_cancellation_scope(None), connect(self.paths.reports_db(self.account_id)) as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    for member_id, relative_path in current.new_files:
                        if connection.execute("SELECT 1 FROM report_sources WHERE relative_path=?", (relative_path,)).fetchone() is None:
                            from backend.app.repositories.reports.transaction import ReportTransaction
                            self.facts.enqueue_file_cleanup(ReportTransaction(connection), member_id, relative_path)
                with tool_cancellation_scope(None):
                    self.drain_file_cleanup()
            raise
