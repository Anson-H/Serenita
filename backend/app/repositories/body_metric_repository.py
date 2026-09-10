from dataclasses import asdict
from backend.app.core.pagination import seek_cursor, seek_position
from backend.app.domain.body_metric_statistics import SERIES_FIELDS, series_key
import hashlib
import json
from contextlib import contextmanager
from uuid import uuid4
from zoneinfo import ZoneInfo
from backend.app.domain.body_metric_statistics import record_date
from backend.app.core.time import local_now
from backend.app.schemas.body_metric import BodyRecord
from backend.app.domain.body_records import RecordFilter, identity, updated_record
from backend.app.core.values import dump, digest
from backend.app.storage.body_metric_database import (
    BODY_METRIC_DATABASE_SCHEMA as SCHEMA,
)
from backend.app.storage.sqlite import connect
from backend.app.storage.database_lifecycle import ensure_database


class BodyMetricRepository:
    def __init__(self, account_id, paths):
        self.account_id, self.paths = account_id, paths

    @contextmanager
    def transaction(self, write=False):
        path = self.paths.body_metrics_db(self.account_id)
        ensure_database(SCHEMA, path)
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db

    def detail(self, db, member, record_id):
        row = db.execute(
            "SELECT * FROM body_records WHERE member_id=? AND record_id=?",
            (member, record_id),
        ).fetchone()
        if not row:
            raise LookupError("记录已删除或不属于当前成员。")
        value = json.loads(row["payload"])
        return {
            **value,
            "record_id": record_id,
            "member_id": member,
            "import_managed": bool(row["import_managed"]),
            "edited": bool(row["edited"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "files": [
                dict(f)
                for f in db.execute(
                    "SELECT file_id,filename,mime_type,sha256 FROM body_files WHERE record_id=? AND member_id=?",
                    (record_id, member),
                )
            ],
        }

    def read(self, member, record_id):
        with self.transaction() as db:
            return self.detail(db, member, record_id)

    @staticmethod
    def record_value(row):
        return {
            **json.loads(row["payload"]),
            **{
                key: row[key]
                for key in ("record_id", "member_id", "created_at", "updated_at")
            },
            "edited": bool(row["edited"]),
            "import_managed": bool(row["import_managed"]),
        }

    def records(self, member, filters=None, *, offset=0, limit=None, statistics=False):
        where, values = (filters or RecordFilter()).sql(member)
        with self.transaction() as db:
            projection = (
                "json_remove(payload,'$.notes','$.data.foods','$.data.stages','$.data.basis','$.data.score_basis') AS payload"
                if statistics
                else "payload"
            )
            query = (
                "SELECT record_id,member_id,created_at,updated_at,edited,import_managed,"
                + projection
                + " FROM body_records WHERE "
                + where
                + " ORDER BY starts_at DESC,record_id"
            )
            if limit is not None:
                query += " LIMIT ? OFFSET ?"
                values.extend([limit, offset])
            return [self.record_value(row) for row in db.execute(query, values)]

    def page(self, member, filters, offset, limit):
        where, values = filters.sql(member)
        with self.transaction() as db:
            total = db.execute(
                "SELECT count(*) FROM body_records WHERE " + where, values
            ).fetchone()[0]
            rows = db.execute(
                "SELECT record_id,member_id,created_at,updated_at,edited,import_managed,payload FROM body_records WHERE "
                + where
                + " ORDER BY starts_at DESC,record_id LIMIT ? OFFSET ?",
                [*values, limit, offset],
            )
            return {
                "items": [self.record_value(row) for row in rows],
                "total": total,
                "next_offset": offset + limit if offset + limit < total else None,
            }

    def sources(self, member):
        with self.transaction() as db:
            return [
                row[0]
                for row in db.execute(
                    "SELECT DISTINCT source FROM body_records WHERE member_id=? ORDER BY source",
                    (member,),
                )
            ]

    def series_records(self, member, filters, series_id, *, cursor=None, limit=None):
        """Resolve dimensions without loading record JSON, then read only this series/page."""
        where, values = filters.sql(member)
        path = self.paths.body_metrics_db(self.account_id)
        with self.transaction() as db:
            stamp = path.stat()
            scope = [
                self.account_id,
                member,
                asdict(filters),
                series_id,
                stamp.st_ino,
                stamp.st_mtime_ns,
                stamp.st_size,
            ]
            position = seek_position(cursor, scope=scope, size=2)
            dimensions = db.execute(
                "SELECT DISTINCT kind,metric,source,json_extract(payload,'$.device') AS device,"
                "json_extract(payload,'$.data.method') AS method,json_extract(payload,'$.data.unit') AS unit,"
                "json_extract(payload,'$.data.score_max') AS score_max FROM body_records WHERE "
                + where,
                values,
            )
            selected = None
            for row in dimensions:
                metrics = (
                    [row["metric"]]
                    if row["kind"] == "measurement"
                    else SERIES_FIELDS[row["kind"]]
                )
                for metric in metrics:
                    key = series_key(
                        metric,
                        row["source"],
                        row["device"],
                        dict(row),
                        measurement=row["kind"] == "measurement",
                    )
                    if digest(key) == series_id:
                        selected = (row, metric)
                        break
                if selected:
                    break
            if selected is None:
                raise LookupError("统计序列不存在于当前范围。")
            row, metric = selected
            field = (
                "value"
                if row["kind"] == "measurement"
                else SERIES_FIELDS[row["kind"]][metric]
            )
            clauses = [
                where,
                "kind=?",
                "metric=?",
                "source=?",
                "json_extract(payload,'$.device')=?",
                f"json_extract(payload,'$.data.{field}') IS NOT NULL",
            ]
            arguments = [
                *values,
                row["kind"],
                row["metric"],
                row["source"],
                row["device"],
            ]
            if row["kind"] == "measurement":
                clauses += [
                    "json_extract(payload,'$.data.method')=?",
                    "json_extract(payload,'$.data.unit')=?",
                ]
                arguments += [row["method"], row["unit"]]
            if metric == "sleep_score":
                clauses += [
                    "json_extract(payload,'$.data.score_max')=?",
                    "json_extract(payload,'$.data.score_stale')=0",
                ]
                arguments.append(row["score_max"])
            predicate = " AND ".join(clauses)
            total = db.execute(
                "SELECT count(*) FROM body_records WHERE " + predicate, arguments
            ).fetchone()[0]
            if not total:
                raise LookupError("统计序列不存在于当前范围。")
            if position:
                predicate += " AND (starts_at,record_id)>(?,?)"
                arguments += position
            query = (
                "SELECT record_id,member_id,created_at,updated_at,edited,import_managed,"
                + (
                    "json_remove(payload,'$.notes','$.data.foods','$.data.stages','$.data.basis','$.data.score_basis') AS payload "
                )
                + "FROM body_records WHERE "
                + predicate
                + " ORDER BY starts_at,record_id"
            )
            if limit is not None:
                query += " LIMIT ?"
                arguments.append(limit + 1)
            records = [self.record_value(item) for item in db.execute(query, arguments)]
            more = limit is not None and len(records) > limit
            if more:
                records = records[:limit]
            next_cursor = (
                seek_cursor(scope, [records[-1]["starts_at"], records[-1]["record_id"]])
                if more
                else None
            )
            return records, metric, total, next_cursor

    def insert(
        self,
        db,
        member,
        payload,
        *,
        key=None,
        import_managed=False,
        source_payload=None,
    ):
        value = BodyRecord.model_validate(payload).model_dump()
        key = key or identity(value)
        found = db.execute(
            "SELECT record_id FROM body_records WHERE member_id=? AND identity_key=?",
            (member, key),
        ).fetchone()
        if found:
            return found["record_id"], False
        if db.execute(
            "SELECT 1 FROM body_exclusions WHERE member_id=? AND identity_key=?",
            (member, key),
        ).fetchone():
            return None, False
        record_id = str(uuid4())
        now = local_now().isoformat()
        row = dict(zip(SCHEMA.table_by_name['body_records'].column_names, (
            record_id, member, value['kind'], value['metric'], value['starts_at'], value['ends_at'],
            value['source'], key, dump(value), dump(payload if source_payload is None else source_payload),
            int(import_managed), 0, now, now,
        )))
        SCHEMA.table_by_name['body_records'].validate_values(row)
        db.execute('INSERT INTO body_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', tuple(row.values()))
        return record_id, True

    def create(self, member, payload, request_id=None):
        with self.transaction(True) as db:
            key = digest(["request", request_id]) if request_id else None
            if key:
                old = db.execute(
                    "SELECT source_payload FROM body_records WHERE member_id=? AND identity_key=?",
                    (member, key),
                ).fetchone()
                if old and json.loads(old["source_payload"]) != payload:
                    raise ValueError("同一请求标识不能提交不同内容。")
            record_id, _ = self.insert(db, member, payload, key=key)
            if not record_id:
                raise ValueError("该来源记录已被删除；请创建新的手工记录。")
            return self.detail(db, member, record_id)

    def update(self, member, record_id, changes):
        with self.transaction(True) as db:
            old = self.detail(db, member, record_id)
            value, changed = updated_record(old, changes)
            if not changed:
                return old
            db.execute(
                "UPDATE body_records SET metric=?,starts_at=?,ends_at=?,payload=?,import_managed=0,edited=1,updated_at=? WHERE record_id=? AND member_id=?",
                (
                    value["metric"],
                    value["starts_at"],
                    value["ends_at"],
                    dump(value),
                    local_now().isoformat(),
                    record_id,
                    member,
                ),
            )
            return self.detail(db, member, record_id)

    @staticmethod
    def retain_record(db, member, record_id):
        db.execute(
            "UPDATE body_records SET import_managed=0,edited=1,updated_at=? WHERE member_id=? AND record_id=?",
            (local_now().isoformat(), member, record_id),
        )

    def delete(self, member, record_id):
        with self.transaction(True) as db:
            self.detail(db, member, record_id)
            db.execute(
                "INSERT OR IGNORE INTO body_exclusions SELECT member_id,identity_key FROM body_records WHERE record_id=? AND member_id=?",
                (record_id, member),
            )
            db.execute(
                "DELETE FROM body_records WHERE record_id=? AND member_id=?",
                (record_id, member),
            )
        return {"deleted": True, "record_id": record_id}

    def attach(self, member, record_id, filename, mime, content):
        SCHEMA.table_by_name['body_files'].validate_values(dict(member_id=member, record_id=record_id, filename=filename, mime_type=mime, image_bytes=content), partial=True)
        sha = hashlib.sha256(content).hexdigest()
        with self.transaction(True) as db:
            record = self.detail(db, member, record_id)
            if record["kind"] != "meal":
                raise ValueError("图片只能关联饮食记录。")
            existing = db.execute(
                "SELECT file_id FROM body_files WHERE record_id=? AND sha256=?",
                (record_id, sha),
            ).fetchone()
            file_id = existing["file_id"] if existing else str(uuid4())
            if not existing:
                db.execute(
                    "INSERT INTO body_files VALUES (?,?,?,?,?,?,?,?)",
                    (
                        file_id,
                        member,
                        record_id,
                        filename,
                        mime,
                        sha,
                        content,
                        local_now().isoformat(),
                    ),
                )
                self.retain_record(db, member, record_id)
            return self.detail(db, member, record_id)

    def file(self, member, record_id, file_id):
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM body_files WHERE member_id=? AND record_id=? AND file_id=?",
                (member, record_id, file_id),
            ).fetchone()
            if not row:
                raise LookupError("图片已不存在。")
            return dict(row)

    def detach(self, member, record_id, file_id):
        with self.transaction(True) as db:
            self.detail(db, member, record_id)
            removed = db.execute(
                "DELETE FROM body_files WHERE member_id=? AND record_id=? AND file_id=?",
                (member, record_id, file_id),
            ).rowcount
            if removed:
                self.retain_record(db, member, record_id)
            return self.detail(db, member, record_id)

    def preview(self, member, filename, sha, parsed, actor, request_id, timezone):
        with self.transaction(True) as db:
            existing = db.execute(
                "SELECT import_id,sha256,payload FROM body_imports WHERE member_id=? AND actor_account_id=? AND request_id=?",
                (member, actor, request_id),
            ).fetchone()
            if existing:
                if (
                    existing["sha256"] != sha
                    or json.loads(existing["payload"])["timezone"] != timezone
                ):
                    raise ValueError("同一请求标识不能用于不同文件或时区。")
                return self.import_detail(db, member, existing["import_id"])
            import_id = str(uuid4())
            now = local_now().isoformat()
            keys = {
                r["identity_key"]
                for r in db.execute(
                    "SELECT identity_key FROM body_records WHERE member_id=? UNION SELECT identity_key FROM body_exclusions WHERE member_id=?",
                    (member, member),
                )
            }
            seen = set()
            duplicates = 0
            for r in parsed["records"]:
                key = identity(r)
                if key in keys or key in seen:
                    duplicates += 1
                seen.add(key)
            dates = sorted(
                record_date(r, ZoneInfo(timezone)) for r in parsed["records"]
            )
            summary = {
                "date_from": dates[0] if dates else None,
                "date_to": dates[-1] if dates else None,
                "categories": sorted(
                    {r["metric"] or r["kind"] for r in parsed["records"]}
                ),
            }
            parsed = {
                **parsed,
                **summary,
                "timezone": timezone,
                "duplicates": duplicates,
                "new_count": len(parsed["records"]) - duplicates,
                "inserted": 0,
                "error": None,
                "selection": None,
            }
            SCHEMA.table_by_name['body_imports'].validate_values(dict(import_id=import_id, member_id=member, actor_account_id=actor, request_id=request_id, filename=filename, sha256=sha, payload=dump(parsed), state='preview', created_at=now, updated_at=now))
            db.execute(
                "INSERT INTO body_imports VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    import_id,
                    member,
                    actor,
                    request_id,
                    filename,
                    sha,
                    dump(parsed),
                    "preview",
                    now,
                    now,
                ),
            )
            return self.import_detail(db, member, import_id)

    def import_detail(self, db, member, import_id):
        row = db.execute(
            """SELECT import_id, filename, state, created_at, updated_at,
            json_remove(payload, '$.records') AS summary
            FROM body_imports WHERE member_id=? AND import_id=?""",
            (member, import_id),
        ).fetchone()
        if not row:
            raise LookupError("导入任务已不存在。")
        return self.import_summary(row)

    @staticmethod
    def import_summary(row):
        return {
            **json.loads(row["summary"]),
            "import_id": row["import_id"],
            "filename": row["filename"],
            "state": row["state"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def imports(self, member, import_id=None, *, cursor=None, limit=24):
        with self.transaction() as db:
            if import_id:
                return self.import_detail(db, member, import_id)
            if type(limit) is not int or not 1 <= limit <= 100:
                raise ValueError("每页数量须为 1 至 100。")
            scope = [self.account_id, member, "body_imports"]
            position = seek_position(cursor, scope=scope, size=2)
            where, parameters = "member_id = ?", [member]
            if position:
                where += " AND (created_at, import_id) < (?, ?)"
                parameters.extend(position)
            rows = db.execute(
                """SELECT import_id, filename, state, created_at, updated_at,
                json_remove(payload, '$.records') AS summary FROM body_imports WHERE """
                + where + " ORDER BY created_at DESC, import_id DESC LIMIT ?",
                [*parameters, limit + 1],
            ).fetchall()
            items = [self.import_summary(row) for row in rows[:limit]]
            following = seek_cursor(scope, [items[-1]["created_at"], items[-1]["import_id"]]) if len(rows) > limit else None
            return {"items": items, "next_cursor": following, "has_more": following is not None}

    def begin_import(self, member, import_id, selection):
        with self.transaction(True) as db:
            item = self.import_detail(db, member, import_id)
            if item["state"] == "complete":
                return item
            row = db.execute(
                "SELECT payload FROM body_imports WHERE import_id=?", (import_id,)
            ).fetchone()
            payload = json.loads(row["payload"])
            if item["state"] == "running" and payload["selection"] != selection:
                raise ValueError("正在处理的导入范围不可更新。")
            payload.update(selection=selection, error=None)
            db.execute(
                "UPDATE body_imports SET state=?,payload=?,updated_at=? WHERE import_id=?",
                ("running", dump(payload), local_now().isoformat(), import_id),
            )
            return self.import_detail(db, member, import_id)

    def commit_import(self, member, import_id):
        from backend.app.domain.body_metric_statistics import select

        with self.transaction(True) as db:
            item = self.import_detail(db, member, import_id)
            if item["state"] == "complete":
                return item
            row = db.execute(
                "SELECT payload FROM body_imports WHERE import_id=?", (import_id,)
            ).fetchone()
            payload = json.loads(row["payload"])
            selection = payload.get("selection") or {}
            records = select(
                payload["records"],
                after=selection.get("after"),
                before=selection.get("before"),
                timezone=payload["timezone"],
            )
            if selection.get("categories"):
                records = [
                    r
                    for r in records
                    if (r["metric"] or r["kind"]) in selection["categories"]
                ]
            inserted = 0
            for r in records:
                source_payload = r["_source_payload"]
                value = {
                    key: item for key, item in r.items() if key != "_source_payload"
                }
                record_id, new = self.insert(
                    db,
                    member,
                    value,
                    import_managed=True,
                    source_payload=source_payload,
                )
                inserted += int(new)
                if record_id:
                    db.execute(
                        "INSERT OR IGNORE INTO body_import_records VALUES (?,?)",
                        (import_id, record_id),
                    )
            payload.update(inserted=inserted, selected_count=len(records), error=None)
            # Parsed upload data is no longer retained once the batch is committed.
            payload["records"] = []
            db.execute(
                "UPDATE body_imports SET state=?,payload=?,updated_at=? WHERE import_id=?",
                ("complete", dump(payload), local_now().isoformat(), import_id),
            )
            return self.import_detail(db, member, import_id)

    def fail_import(self, member, import_id, error):
        with self.transaction(True) as db:
            row = db.execute(
                "SELECT payload FROM body_imports WHERE member_id=? AND import_id=?",
                (member, import_id),
            ).fetchone()
            if not row:
                return
            payload = json.loads(row["payload"])
            payload["error"] = error
            db.execute(
                "UPDATE body_imports SET state=?,payload=?,updated_at=? WHERE member_id=? AND import_id=?",
                ("failed", dump(payload), local_now().isoformat(), member, import_id),
            )

    def delete_import(self, member, import_id):
        with self.transaction(True) as db:
            self.import_detail(db, member, import_id)
            ids = [
                r["record_id"]
                for r in db.execute(
                    "SELECT record_id FROM body_import_records WHERE import_id=?",
                    (import_id,),
                )
            ]
            db.execute(
                "DELETE FROM body_imports WHERE import_id=? AND member_id=?",
                (import_id, member),
            )
            deleted = 0
            for record_id in ids:
                record = db.execute(
                    "SELECT import_managed FROM body_records WHERE record_id=? AND member_id=?",
                    (record_id, member),
                ).fetchone()
                if not record or not record["import_managed"]:
                    continue
                if db.execute(
                    "SELECT 1 FROM body_import_records WHERE record_id=?", (record_id,)
                ).fetchone():
                    continue
                db.execute(
                    "INSERT OR IGNORE INTO body_exclusions SELECT member_id,identity_key FROM body_records WHERE record_id=? AND member_id=?",
                    (record_id, member),
                )
                deleted += db.execute(
                    "DELETE FROM body_records WHERE record_id=? AND member_id=?",
                    (record_id, member),
                ).rowcount
            return {
                "deleted": True,
                "records_deleted": deleted,
                "records_retained": len(ids) - deleted,
            }
