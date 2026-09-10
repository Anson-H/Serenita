from __future__ import annotations

from typing import Any, Iterable, Optional
from backend.app.storage.sqlite import connect
from backend.app.repositories.report_values import _row_dict
from backend.app.schemas.report import REPORT_TYPED_FIELDS, REPORT_STRUCTURES


class ReportQueries:
    """Report catalogues and fact snapshots sharing the repository transaction boundary."""

    def report_exists(self, member_id: str, report_id: str) -> bool:
        self.init_db()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            row = connection.execute(
                "SELECT 1 FROM reports WHERE member_id = ? AND report_id = ?",
                (member_id, report_id),
            ).fetchone()
        return row is not None

    def report_catalog(self, member_id, *, before_date=None, after_date=None, cursor=None, limit=24):
        from backend.app.core.pagination import seek_cursor, seek_position

        self.init_db()
        scope = [self.account_id, member_id, before_date, after_date]
        position = seek_position(cursor, scope=scope, size=2)
        clauses, parameters = ["member_id = ?"], [member_id]
        for bound, operator in ((before_date, "<="), (after_date, ">=")):
            if bound:
                clauses.append(f"substr(report_time, 1, 10) {operator} ?")
                parameters.append(bound)
        with connect(self.paths.reports_db(self.account_id)) as connection:
            connection.execute("BEGIN")
            total = connection.execute("SELECT count(*) FROM reports WHERE " + " AND ".join(clauses), parameters).fetchone()[0]
            if position:
                clauses.append("(report_time, report_id) < (?, ?)")
                parameters.extend(position)
            rows = connection.execute(
                "SELECT report_id, report_type, report_name, report_time FROM reports WHERE "
                + " AND ".join(clauses) + " ORDER BY report_time DESC, report_id DESC LIMIT ?",
                [*parameters, limit + 1],
            ).fetchall()
        items = [dict(row) for row in rows[:limit]]
        following = seek_cursor(scope, [items[-1]["report_time"], items[-1]["report_id"]]) if len(rows) > limit else None
        return {"reports": items, "report_ids": [item["report_id"] for item in items], "total": total, "next_cursor": following}

    def list_reports(
        self,
        member_id: str,
        *,
        report_type: Optional[str] = None,
    ) -> dict[str, Any]:
        self.init_db()
        clauses = ["r.member_id = ?"]
        parameters: list[Any] = [member_id]
        if report_type:
            clauses.append("r.report_type = ?")
            parameters.append(report_type)
        query = f"""
            SELECT r.report_id, r.member_id, r.report_type, r.report_name,
                   r.report_time,
                   r.institution_name, r.analysis_content, r.analysis_outdated,
                   r.analysis_updated_at,
                   r.created_at, r.updated_at,
                   CASE WHEN r.report_type = '检验报告'
                        THEN (SELECT COUNT(*) FROM lab_test_report l
                              WHERE l.report_id = r.report_id AND l.member_id = r.member_id)
                        ELSE 1 END AS total_count,
                   CASE WHEN r.report_type = '检验报告'
                        THEN (SELECT COUNT(*) FROM lab_test_report l
                              WHERE l.report_id = r.report_id AND l.member_id = r.member_id
                                AND l.flag_text IN ('异常', '偏高', '偏低'))
                        ELSE 0 END AS flagged_count
            FROM reports r
            WHERE {" AND ".join(clauses)}
            ORDER BY r.report_time DESC, r.created_at DESC
        """
        with connect(self.paths.reports_db(self.account_id)) as connection:
            rows = connection.execute(query, parameters).fetchall()
        reports = [self._list_item(row) for row in rows]
        return {"reports": reports, "total": len(reports)}

    def get_report(self, member_id: str, report_id: str) -> Optional[dict[str, Any]]:
        return self.get_report_detail(member_id, report_id)

    def get_report_detail(self, member_id: str, report_id: str) -> Optional[dict[str, Any]]:
        values = self.report_evidence(member_id, [report_id])
        return values[0] if values else None

    def report_evidence(self, member_id: str, report_ids: Optional[Iterable[str]] = None) -> list[dict[str, Any]]:
        requested = list(dict.fromkeys(report_ids)) if report_ids is not None else None
        if requested == []:
            return []
        with self.transaction() as transaction:
            db = transaction.connection
            if requested is None:
                rows = db.execute(
                    "SELECT * FROM reports WHERE member_id = ? ORDER BY report_time DESC, created_at DESC",
                    (member_id,),
                ).fetchall()
            else:
                rows = []
                for offset in range(0, len(requested), 400):
                    batch = requested[offset:offset + 400]
                    rows.extend(db.execute(
                        "SELECT * FROM reports WHERE member_id = ? AND report_id IN (" + ",".join("?" for _ in batch) + ")",
                        (member_id, *batch),
                    ).fetchall())
            details = {row["report_id"]: {
                **dict(row), "analysis_content": str(row["analysis_content"] or ""),
                "analysis_outdated": bool(row["analysis_outdated"]),
                "has_analysis": bool(str(row["analysis_content"] or "").strip()),
                "sources": [], "lab_test_results": [],
                **{table: None for table in REPORT_TYPED_FIELDS},
            } for row in rows}
            ids = list(details)
            for offset in range(0, len(ids), 400):
                batch = ids[offset:offset + 400]
                placeholders = ",".join("?" for _ in batch)
                for source in db.execute(
                    """SELECT l.report_id, f.resource_id, f.mime_type, f.size_bytes,
                    f.source_kind, f.relative_path, f.created_at, l.is_primary
                    FROM report_source_links l JOIN report_sources f
                    ON f.resource_id = l.resource_id AND f.member_id = l.member_id
                    WHERE l.member_id = ? AND l.report_id IN (""" + placeholders + ") ORDER BY l.is_primary DESC, l.created_at",
                    (member_id, *batch),
                ):
                    value = dict(source)
                    report_id = value.pop("report_id")
                    value["is_primary"] = bool(value["is_primary"])
                    details[report_id]["sources"].append(value)
                if any(details[value]["report_type"] == "检验报告" for value in batch):
                    for row in db.execute(
                        "SELECT * FROM lab_test_report WHERE member_id = ? AND report_id IN (" + placeholders + ") ORDER BY item_name_zh",
                        (member_id, *batch),
                    ):
                        details[row["report_id"]]["lab_test_results"].append(dict(row))
                for report_type, (table, _model) in REPORT_STRUCTURES.items():
                    if not any(details[value]["report_type"] == report_type for value in batch):
                        continue
                    for row in db.execute(
                        f"SELECT * FROM {table} WHERE member_id = ? AND report_id IN (" + placeholders + ")",
                        (member_id, *batch),
                    ):
                        details[row["report_id"]][table] = dict(row)
        return [details[value] for value in (requested if requested is not None else ids) if value in details]

    def lab_indicator_snapshot(
        self, member_id: str, report_id: str, item_id: str
    ) -> Optional[dict[str, Any]]:
        self.init_db()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            row = connection.execute(
                """
                SELECT report_id, item_id, item_name_zh, result_text, reference_text, flag_text
                FROM lab_test_report
                WHERE member_id = ? AND report_id = ? AND item_id = ?
                """,
                (member_id, report_id, item_id),
            ).fetchone()
        return _row_dict(row)

    def _list_item(self, row) -> dict[str, Any]:
        analysis_content = str(row["analysis_content"] or "")
        return {
            "report_id": row["report_id"],
            "member_id": row["member_id"],
            "report_type": row["report_type"],
            "report_name": row["report_name"],
            "report_time": row["report_time"],
            "institution_name": row["institution_name"],
            "flagged_count": row["flagged_count"],
            "total_count": row["total_count"],
            "has_analysis": bool(analysis_content.strip()),
            "analysis_outdated": bool(row["analysis_outdated"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
