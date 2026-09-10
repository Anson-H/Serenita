"""Authorized body record operations and bounded statistical views."""

import hashlib
import logging
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import asdict
from threading import Lock
from uuid import uuid4
from zoneinfo import ZoneInfoNotFoundError
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from backend.app.application.body_metric_import import parse_file
from backend.app.core.errors import raise_error
from backend.app.domain.body_records import RecordFilter
from backend.app.domain.body_metric_statistics import (
    stats,
    record_date,
    original_point,
    record_values,
)
from zoneinfo import ZoneInfo
from backend.app.core.pagination import collection_page
from backend.app.repositories.member_repository import MemberRepository
from backend.app.repositories.body_metric_repository import BodyMetricRepository
from backend.app.schemas.body_metric import CATALOG, MEALS, STAGES

log = logging.getLogger(__name__)


class BodyMetricService:
    def __init__(self, members=None):
        self.members = members or MemberRepository()
        self.jobs = set()
        self.lock = Lock()
        self.statistics_cache = OrderedDict()

    @contextmanager
    def repository(self, actor, member, *, write=False):
        with self.members.access_guard(actor, member, write=write) as access:
            with self.record_errors():
                yield BodyMetricRepository(access.account_id, self.members.paths)

    @staticmethod
    @contextmanager
    def record_errors():
        try:
            yield
        except ZoneInfoNotFoundError:
            raise_error("invalid_input", "BODY_RECORD_INVALID", "时区无效。")
        except LookupError as exc:
            raise_error("missing", "BODY_RECORD_NOT_FOUND", str(exc))
        except (ValueError, TypeError, ParseError, BadZipFile) as exc:
            raise_error("invalid_input", "BODY_RECORD_INVALID", str(exc))

    def catalog(self, actor, member):
        with self.repository(actor, member):
            return {
                "metrics": list(CATALOG.values()),
                "meal_types": MEALS,
                "stages": STAGES,
            }

    def query(
        self,
        actor,
        member,
        after=None,
        before=None,
        category=None,
        source=None,
        timezone="Asia/Shanghai",
        offset=0,
        limit=100,
    ):
        with self.repository(actor, member) as repo:
            filters = RecordFilter(after, before, category, source, timezone)
            if offset < 0 or not 1 <= limit <= 1000:
                raise ValueError("分页数量须为 1 至 1000。")
            return repo.page(member, filters, offset, limit)

    def _statistics(self, repo, member, filters):
        path = repo.paths.body_metrics_db(repo.account_id)
        stamp = path.stat() if path.exists() else None
        revision = (stamp.st_ino, stamp.st_mtime_ns, stamp.st_size) if stamp else None
        key = (repo.account_id, member, filters, revision)
        with self.lock:
            if key in self.statistics_cache:
                self.statistics_cache.move_to_end(key)
                return self.statistics_cache[key]
        records = repo.records(member, filters, statistics=True)
        result = {
            "series": stats(records, filters.timezone, filters.after, filters.before),
            "total_records": len(records),
            "sources": repo.sources(member),
        }
        zone = ZoneInfo(filters.timezone)
        dates = sorted({record_date(record, zone) for record in records})
        result.update(
            coverage_from=min((r["starts_at"] for r in records), default=None),
            coverage_to=max(
                (r["ends_at"] or r["starts_at"] for r in records), default=None
            ),
            coverage_dates={
                "first": dates[0] if dates else None,
                "last": dates[-1] if dates else None,
                "recorded_days": len(dates),
            },
            missing_values={
                key: sum(
                    r["kind"] == kind and r["data"].get(key) is None for r in records
                )
                for kind, keys in [
                    ("meal", ("energy", "carbohydrate", "protein", "fat")),
                    ("sleep", ("duration_minutes", "score")),
                ]
                for key in keys
            },
        )
        result["excluded_stale_scores"] = sum(
            r["kind"] == "sleep"
            and r["data"].get("score") is not None
            and r["data"].get("score_stale", False)
            for r in records
        )
        if len(records) <= 50000:
            with self.lock:
                self.statistics_cache[key] = result
                while len(self.statistics_cache) > 4:
                    self.statistics_cache.popitem(last=False)
        return result

    def statistics(
        self,
        actor,
        member,
        after=None,
        before=None,
        category=None,
        source=None,
        timezone="Asia/Shanghai",
    ):
        with self.repository(actor, member) as repo:
            result = self._statistics(
                repo, member, RecordFilter(after, before, category, source, timezone)
            )
            return {
                **result,
                "series": [
                    {
                        **{
                            k: v for k, v in s.items() if k not in ("points", "buckets")
                        },
                        "preview": [
                            {"date": b["date"], "value": b["value"]}
                            for b in s["buckets"][-12:]
                        ],
                    }
                    for s in result["series"]
                ],
            }

    def series_data(
        self,
        actor,
        member,
        series_id,
        *,
        view="buckets",
        cursor=None,
        limit=100,
        after=None,
        before=None,
        category=None,
        source=None,
        timezone="Asia/Shanghai",
    ):
        with self.repository(actor, member) as repo:
            if view not in ("buckets", "points"):
                raise ValueError("序列视图必须为 buckets 或 points。")
            filters = RecordFilter(after, before, category, source, timezone)
            if type(limit) is not int or not 1 <= limit <= 1000:
                raise ValueError("每页数量须为 1 至 1000。")
            records, metric, total, next_cursor = repo.series_records(
                member,
                filters,
                series_id,
                cursor=cursor if view == "points" else None,
                limit=limit if view == "points" else None,
            )
            if view == "points":
                zone = ZoneInfo(timezone)
                return {
                    "items": [
                        original_point(record, record_values(record)[metric], zone)
                        for record in records
                    ],
                    "total": total,
                    "next_cursor": next_cursor,
                }
            series = next(
                item
                for item in stats(records, timezone, after, before)
                if item["series_id"] == series_id
            )
            return collection_page(
                [
                    {key: value for key, value in item.items() if key != "record_ids"}
                    for item in series["buckets"]
                ],
                cursor=cursor,
                limit=limit,
                maximum=1000,
                scope=[repo.account_id, member, series_id, view, asdict(filters)],
            )

    def create(self, actor, member, values, request_id=None):
        with self.repository(actor, member, write=True) as repo:
            return repo.create(member, values, request_id)

    def read(self, actor, member, record_id):
        with self.repository(actor, member) as repo:
            return repo.read(member, record_id)

    def update(self, actor, member, record_id, changes):
        with self.repository(actor, member, write=True) as repo:
            return repo.update(member, record_id, changes)

    def delete(self, actor, member, record_id):
        with self.repository(actor, member, write=True) as repo:
            return repo.delete(member, record_id)

    def attach(self, actor, member, record_id, filename, mime, content):
        with self.repository(actor, member, write=True) as repo:
            if len(content) > 10 * 1024 * 1024:
                raise ValueError("图片超过 10 MiB。")
            if not (
                (mime == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n"))
                or (mime == "image/jpeg" and content.startswith(b"\xff\xd8\xff"))
                or (
                    mime == "image/webp"
                    and content[:4] == b"RIFF"
                    and content[8:12] == b"WEBP"
                )
            ):
                raise ValueError("请选择有效 PNG、JPEG 或 WebP 图片。")
            return repo.attach(member, record_id, filename, mime, content)

    def file(self, actor, member, record_id, file_id):
        with self.repository(actor, member) as repo:
            return repo.file(member, record_id, file_id)

    def detach(self, actor, member, record_id, file_id):
        with self.repository(actor, member, write=True) as repo:
            return repo.detach(member, record_id, file_id)

    def preview(
        self,
        actor,
        member,
        filename,
        content,
        request_id=None,
        timezone="Asia/Shanghai",
    ):
        with self.repository(actor, member, write=True):
            pass
        with self.record_errors():
            RecordFilter(timezone=timezone)
            request_id = request_id or str(uuid4())
            if (
                not isinstance(request_id, str)
                or not request_id.strip()
                or len(request_id) > 200
            ):
                raise ValueError("导入请求标识须为 1 至 200 字符。")
            parsed = parse_file(filename, content)
        with self.repository(actor, member, write=True) as repo:
            return repo.preview(
                member,
                filename,
                hashlib.sha256(content).hexdigest(),
                parsed,
                actor,
                request_id,
                timezone,
            )

    def imports(self, actor, member, import_id=None, *, cursor=None, limit=24):
        with self.repository(actor, member) as repo:
            return repo.imports(member, import_id, cursor=cursor, limit=limit)

    def delete_import(self, actor, member, import_id):
        with self.repository(actor, member, write=True) as repo:
            return repo.delete_import(member, import_id)

    def start_import(self, actor, member, import_id, selection):
        with self.repository(actor, member, write=True) as repo:
            if set(selection) - {"after", "before", "categories"}:
                raise ValueError("导入范围字段不合法。")
            RecordFilter(selection.get("after"), selection.get("before"))
            if "categories" in selection:
                categories = selection["categories"]
                if (
                    not isinstance(categories, list)
                    or not categories
                    or any(
                        not isinstance(c, str)
                        or c not in {*CATALOG, "meal", "sleep", "workout"}
                        for c in categories
                    )
                ):
                    raise ValueError("指标筛选必须为非空分类数组。")
            key = (member, import_id)
            with self.lock:
                if key in self.jobs:
                    return repo.imports(member, import_id), False
                item = repo.begin_import(member, import_id, selection)
                if item["state"] == "complete":
                    return item, False
                self.jobs.add(key)
            return item, True

    def run_import(self, actor, member, import_id):
        try:
            with self.repository(actor, member, write=True) as repo:
                repo.commit_import(member, import_id)
        except Exception as exc:
            try:
                with self.repository(actor, member, write=True) as repo:
                    repo.fail_import(member, import_id, str(exc))
            except Exception:
                log.info(
                    "Import outcome could not be saved after access or resource change",
                    exc_info=True,
                )
        finally:
            with self.lock:
                self.jobs.discard((member, import_id))
