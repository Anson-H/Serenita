"""Account medication catalogue with member inventory and plans."""

import base64
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4
from backend.app.core.values import now, dump, digest
from backend.app.core.errors import raise_error
from backend.app.schemas.medication import validate_request_id
from backend.app.domain.medications import plan_status, matches_date
from backend.app.schemas.medication import MODELS, IDS, TABLES, Identity
from backend.app.storage.medication_database import MEDICATION_DATABASE_SCHEMA
from backend.app.storage.sqlite import connect


JSON_FIELDS = {"medication_identity", "schedule"}


def medication_identity_sql():
    fields = ",".join(f"'{name}',d.{name}" for name in Identity.model_fields)
    return f"json_object({fields})"


def encode(values):
    return {
        k: dump(v) if k == "schedule" and v is not None else v
        for k, v in values.items()
    }


def decode(row):
    return {
        k: json.loads(v) if k in JSON_FIELDS and v is not None else v
        for k, v in dict(row).items()
    }


class MedicationRepository:
    def __init__(self, account_id, paths):
        self.account_id, self.paths = account_id, paths

    def init_db(self):
        path = self.paths.medications_db(self.account_id)
        if not MEDICATION_DATABASE_SCHEMA.validate_existing(path):
            with connect(path) as db:
                db.execute("BEGIN IMMEDIATE")
                MEDICATION_DATABASE_SCHEMA.create(db)

    @contextmanager
    def transaction(self, write=False):
        self.init_db()
        with connect() as db:
            stores = [(self.paths.medications_db(self.account_id), "medication_data")]
            for path, alias in sorted(stores):
                db.execute(f"ATTACH DATABASE ? AS {alias}", (str(path),))
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db

    def detail(self, db, member, kind, object_id):
        table, key = TABLES[kind], IDS[kind]
        row = db.execute(
            f"SELECT * FROM medication_data.{table} WHERE {key}=?" + (" AND member_id=?" if kind != "medication" else ""),
            (object_id, member) if kind != "medication" else (object_id,),
        ).fetchone()
        if not row:
            raise LookupError("记录已不存在或不属于当前成员。")
        result = decode(row)
        if kind == "plan":
            result["medication_identity"] = self.medication_identity(db, member, result["medication_id"])
        if kind == "plan":
            result["time_status"] = plan_status(result)[0]
        if kind == "medication":
            if member is not None:
                result["member_id"] = member
            from backend.app.repositories.medication_source_repository import MedicationSourceRepository, public_source
            result["sources"] = [public_source(s) for s in MedicationSourceRepository.list(db, member, object_id)]
            result["batches"] = [
                decode(r)
                for r in db.execute(
                    "SELECT * FROM medication_data.medication_inventory WHERE medication_id=? AND member_id=? ORDER BY expires_on IS NULL,expires_on,created_at",
                    (object_id, member),
                )
            ]
            if member is None:
                result.pop("batches")
        return result

    def read(self, member, kind, object_id):
        with self.transaction() as db:
            return self.detail(db, member, kind, object_id)

    def read_inventory(self, member, medication_id):
        with self.transaction() as db:
            value = self.detail(db, member, 'medication', medication_id)
            return {key: value[key] for key in ('medication_id', 'member_id', 'generic_name', 'brand_name',
                'strength', 'package_specification', 'created_at', 'updated_at', 'batches')}

    def plan_snapshots(self, db, member, ids=None):
        values = [member]
        condition = "m.member_id=?"
        if ids is not None:
            if not ids:
                return {}
            condition += (
                " AND m.medication_plan_id IN (" + ",".join("?" for _ in ids) + ")"
            )
            values.extend(ids)
        plans = {
            row["medication_plan_id"]: decode(row)
            for row in db.execute(
                f"SELECT m.*,{medication_identity_sql()} AS medication_identity "
                "FROM medication_data.medication_plans m JOIN medication_data.medications d ON d.medication_id=m.medication_id WHERE "
                + condition,
                values,
            )
        }
        return plans

    def batch_snapshots(self, db, member, ids=None):
        values = [member]
        condition = "m.member_id=?"
        if ids is not None:
            if not ids:
                return {}
            condition += " AND m.medication_batch_id IN (" + ",".join("?" for _ in ids) + ")"
            values.extend(ids)
        return {
            row["medication_batch_id"]: decode(row)
            for row in db.execute(
                f"SELECT m.*,{medication_identity_sql()} AS medication_identity "
                "FROM medication_data.medication_inventory m JOIN medication_data.medications d "
                "ON d.medication_id=m.medication_id WHERE " + condition,
                values,
            )
        }

    def catalog(self, member, kind, filters, *, medication_fields=None):
        key, table = IDS[kind], TABLES[kind]
        signature = digest(
            {**{k: v for k, v in filters.items() if k not in ("cursor", "limit")},
             **({"fields": sorted(medication_fields)} if medication_fields is not None else {})}
        )
        where, values = (["1=1"], []) if kind == "medication" else (["m.member_id=?"], [member])
        if kind == "medication" and filters.get("inventory_only"):
            where.append("EXISTS (SELECT 1 FROM medication_data.medication_inventory b WHERE b.medication_id=m.medication_id AND b.member_id=?)")
            values.append(member)
        source = f"medication_data.{table} m"
        if kind == "plan":
            source += " JOIN medication_data.medications d ON d.medication_id=m.medication_id"
        with self.transaction() as db:
            if kind == 'plan' and 'medication_plan_id' in filters:
                plan_id = filters['medication_plan_id']
                if not db.execute(
                    f"SELECT 1 FROM medication_data.{table} WHERE {key}=? AND member_id=?",
                    (plan_id, member),
                ).fetchone():
                    raise LookupError("记录已不存在或不属于当前成员。")
                where.append(f"m.{key}=?")
                values.append(plan_id)
            if filters.get("medication_id"):
                if medication_fields is not None and not db.execute(
                    "SELECT 1 FROM medication_data.medications WHERE medication_id=?",
                    (filters['medication_id'],),
                ).fetchone():
                    raise LookupError("记录已不存在或不属于当前成员。")
                where.append("m.medication_id=?")
                values.append(filters["medication_id"])
            cursor_where, cursor_values = [], []
            cursor = filters.get("cursor")
            if cursor:
                try:
                    token = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                    if token["scope"] != [member, kind, signature]:
                        raise ValueError()
                    row = db.execute(
                        f"SELECT created_at FROM medication_data.{table} WHERE {key}=?" + (" AND member_id=?" if kind != "medication" else ""),
                        (token["id"], member) if kind != "medication" else (token["id"],),
                    ).fetchone()
                    if not row:
                        raise ValueError()
                    cursor_where.append(f"(m.created_at,m.{key}) < (?,?)")
                    cursor_values.extend([row["created_at"], token["id"]])
                except (ValueError, KeyError, TypeError):
                    raise ValueError("分页游标失效，请重新读取目录。")
            db.create_function(
                "casefold", 1, lambda text: (text or "").casefold(), deterministic=True
            )
            query = filters.get("query", "").strip().casefold()
            if query:
                columns = [
                    name
                    for name in MODELS[kind].model_fields
                ]
                search = " || char(10) || ".join(
                    f"coalesce(m.{name},'')" for name in columns
                )
                if kind == "plan":
                    search += f" || char(10) || coalesce({medication_identity_sql()},'')"
                where.append(f"instr(casefold({search}),?)>0")
                values.append(query)
            if kind == "plan":
                plan_columns = ",".join(f"'{name}',m.{name}" for name in ("starts_at", "ends_at", "timezone", "usage_status"))
                plan_json = f"json_object({plan_columns})"
                at = datetime.now(timezone.utc)
                db.create_function(
                    "plan_matches",
                    1,
                    lambda text: self._catalog_plan_matches(
                        json.loads(text), filters, at
                    ),
                )
                if any(
                    filters.get(k)
                    for k in ("status", "after_date", "before_date", "undated")
                ):
                    where.append(f"plan_matches({plan_json})")
                projection = f"m.*,{medication_identity_sql()} AS medication_identity"
            elif kind == "medication":
                if medication_fields is None:
                    projection = "m.medication_id,m.generic_name,m.brand_name,m.strength,m.package_specification,m.prescription_type,m.created_at,m.updated_at"
                else:
                    columns = (medication_fields - {'sources'}) | {'medication_id'}
                    projection = ','.join(f'm.{column}' for column in sorted(columns))
            else:
                projection = "m.*"
            limit = filters.get("limit", 24)
            total = db.execute(
                f"SELECT count(*) FROM {source} WHERE {' AND '.join(where)}",
                values,
            ).fetchone()[0]
            where.extend(cursor_where)
            values.extend(cursor_values)
            sql = f"SELECT {projection} FROM {source} WHERE {' AND '.join(where)} ORDER BY m.created_at DESC,m.{key} DESC LIMIT ?"
            rows = db.execute(sql, [*values, limit + 1]).fetchall()
            items = [decode(row) for row in rows[:limit]]
            for item in items:
                if kind == "medication" and member is not None:
                    item["member_id"] = member
                if medication_fields is not None and 'sources' in medication_fields:
                    from backend.app.repositories.medication_source_repository import MedicationSourceRepository, public_source
                    item['sources'] = [public_source(source) for source in MedicationSourceRepository.list(db, member, item['medication_id'])]
                if kind == "plan":
                    item["time_status"] = plan_status(item)[0]
            next_cursor = (
                base64.urlsafe_b64encode(
                    dump(
                        {"id": items[-1][key], "scope": [member, kind, signature]}
                    ).encode()
                ).decode()
                if len(rows) > limit
                else None
            )
            return {"items": items, "total": total, "next_cursor": next_cursor}

    @staticmethod
    def _catalog_plan_matches(plan, filters, at):
        return int(
            (not filters.get("status") or filters["status"] in plan_status(plan, at))
            and matches_date(plan, filters)
        )

    @staticmethod
    def insert(db, table, values, schema="medication_data"):
        MEDICATION_DATABASE_SCHEMA.table_by_name[table].validate_values(values)
        db.execute(
            f"INSERT INTO {schema}.{table} ("
            + ",".join(values)
            + ") VALUES ("
            + ",".join("?" for _ in values)
            + ")",
            tuple(values.values()),
        )

    def request_result(self, db, *, actor, member, request_id, operation, payload_hash):
        """Return a matching committed result within the caller's transaction."""
        validate_request_id(request_id)
        row = db.execute(
            "SELECT * FROM medication_data.medication_requests WHERE actor_account_id=? AND request_id=?",
            (actor, request_id),
        ).fetchone()
        if row is None:
            return None
        if (
            row["member_id"] != member
            or row["operation"] != operation
            or row["payload_hash"] != payload_hash
        ):
            raise_error(
                "conflict", "MEDICATION_REQUEST_CONFLICT",
                "同一请求标识不能用于不同内容。",
            )
        return row["object_id"]

    def record_request(
        self, db, *, actor, member, request_id, operation, payload_hash, object_id
    ):
        """Commit the result identity together with its resource mutation."""
        validate_request_id(request_id)
        self.insert(
            db,
            "medication_requests",
            {
                "actor_account_id": actor,
                "request_id": request_id,
                "member_id": member,
                "object_id": object_id,
                "operation": operation,
                "payload_hash": payload_hash,
                "created_at": now(),
            },
        )

    def medication_identity(self, db, member, medication_id):
        columns = ",".join(Identity.model_fields)
        row = db.execute(
            f"SELECT {columns} FROM medication_data.medications WHERE medication_id=?",
            (medication_id,),
        ).fetchone()
        if row is None:
            raise LookupError("药品已不存在或不属于该健康档案所有者的药品目录。")
        return dict(row)

    def persist(
        self, db, member, kind, values, object_id=None
    ):
        creating = object_id is None
        object_id = object_id or str(uuid4())
        key = IDS[kind]
        values = dict(values)
        if creating:
            self.insert(
                db,
                TABLES[kind],
                {
                    key: object_id,
                    **({"member_id": member} if kind != "medication" else {}),
                    **encode(values),
                    "created_at": now(),
                    "updated_at": now(),
                },
            )
        else:
            payload = {**encode(values), "updated_at": now()}
            previous = db.execute(f"SELECT * FROM medication_data.{TABLES[kind]} WHERE {key}=?", (object_id,)).fetchone()
            if previous is None:
                raise LookupError("记录已不存在。")
            MEDICATION_DATABASE_SCHEMA.table_by_name[TABLES[kind]].validate_values({**dict(previous), **payload})
            db.execute(
                f"UPDATE medication_data.{TABLES[kind]} SET "
                + ",".join(f"{k}=?" for k in payload)
                + f" WHERE {key}=?" + (" AND member_id=?" if kind != "medication" else ""),
                (*payload.values(), object_id, member) if kind != "medication" else (*payload.values(), object_id),
            )
        return object_id

    def delete(self, member, kind, object_id):
        with self.transaction(True) as db:
            self.detail(db, member, kind, object_id)
            if kind == 'medication':
                for table in ('medication_inventory', 'medication_plans'):
                    if db.execute(f'SELECT 1 FROM medication_data.{table} WHERE medication_id=?', (object_id,)).fetchone():
                        raise_error('conflict', 'MEDICATION_IN_USE', '药品仍被库存或用药计划引用，不能删除。')
                queue_sources(db, object_id)
            db.execute(
                f"DELETE FROM medication_data.{TABLES[kind]} WHERE {IDS[kind]}=?" + (" AND member_id=?" if kind != "medication" else ""),
                (object_id, member) if kind != "medication" else (object_id,),
            )
        return {"deleted": True, IDS[kind]: object_id, **({"member_id": member} if member is not None else {})}


def queue_sources(db, medication_id, schema="medication_data"):
    sql = f"SELECT * FROM {schema}.medication_sources WHERE medication_id=?"
    arguments = [medication_id]
    for row in db.execute(sql, arguments).fetchall():
        MedicationRepository.insert(
            db,
            "medication_source_cleanup_outbox",
            {
                "cleanup_id": str(uuid4()),
                "relative_path": row["relative_path"],
                "created_at": now(),
            },
            schema,
        )
