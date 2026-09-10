"""Bounded record materialization and response sizes at supported import scale."""
import json
from datetime import datetime, timedelta, timezone
from time import perf_counter
from contextlib import contextmanager

import pytest
from member_support import accounts as accounts, account_id, create_member
from backend.app.application.body_metric_service import BodyMetricService
from backend.app.repositories.body_metric_repository import BodyMetricRepository
from backend.app.schemas.body_metric import BodyRecord
from backend.app.storage.paths import app_paths


@pytest.mark.parametrize("count", [100, 10_000, 250_000])
def test_body_queries_keep_pages_bounded_with_complete_statistics(accounts, monkeypatch, count):
    owner, *_ = accounts
    member = create_member(owner)
    actor = account_id("owner")
    repository = BodyMetricRepository(actor, app_paths())
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    def rows():
        for index in range(count):
            stamp = (start + timedelta(minutes=index)).isoformat(timespec="microseconds")
            record = BodyRecord.model_validate({
                "kind": "measurement", "metric": "heart_rate", "starts_at": stamp,
                "source": "synthetic", "device": "test", "data": {"value": 60 + index % 40, "unit": "次/分"},
            }).model_dump()
            payload = json.dumps(record, separators=(",", ":"))
            yield (f"record-{index:08d}", member, "measurement", "heart_rate", stamp, None,
                   "synthetic", f"identity-{index}", payload, payload, 0, 0, stamp, stamp)
    with repository.transaction(True) as db:
        db.executemany("INSERT INTO body_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows())
    materialized = 0
    original = BodyMetricRepository.record_value
    def track(row):
        nonlocal materialized
        materialized += 1
        return original(row)
    monkeypatch.setattr(BodyMetricRepository, "record_value", staticmethod(track))
    queries = []
    transaction = BodyMetricRepository.transaction
    @contextmanager
    def traced(self, *args, **kwargs):
        with transaction(self, *args, **kwargs) as db:
            db.set_trace_callback(lambda sql: queries.append(sql) if sql.startswith("SELECT") and "body_records" in sql else None)
            yield db
    monkeypatch.setattr(BodyMetricRepository, "transaction", traced)
    service = BodyMetricService()
    results = {"input_rows": count}
    for name, operation in [
        ("catalog", lambda: service.catalog(actor, member)),
        ("list", lambda: service.query(actor, member, limit=100)),
        ("statistics", lambda: service.statistics(actor, member, timezone="UTC")),
    ]:
        materialized = 0
        queries.clear()
        then = perf_counter()
        output = operation()
        results[name] = {"select_queries": len(queries), "materialized_rows": materialized, "response_bytes": len(json.dumps(output).encode()),
                         "elapsed_ms": round((perf_counter() - then) * 1000, 2)}
        if name == "statistics":
            summary = output
    assert results["catalog"]["materialized_rows"] == 0
    assert results["list"]["materialized_rows"] == 100
    assert summary["total_records"] == summary["series"][0]["count"] == count
    assert results["statistics"]["response_bytes"] < 10_000
    assert "points" not in summary["series"][0]
    series_id = summary["series"][0]["series_id"]
    # A series page must not ask the full-statistics path for all matching records.
    monkeypatch.setattr(service, "_statistics", lambda *a: pytest.fail("series page rebuilt full statistics"))
    materialized = 0
    queries.clear()
    then = perf_counter()
    page = service.series_data(actor, member, series_id, view="points", limit=100, timezone="UTC")
    results["points"] = {"select_queries": len(queries), "materialized_rows": materialized, "response_bytes": len(json.dumps(page).encode()),
                         "elapsed_ms": round((perf_counter() - then) * 1000, 2)}
    assert len(page["items"]) == 100 and page["total"] == count
    assert materialized <= 101
    if page["next_cursor"]:
        next_page = service.series_data(actor, member, series_id, view="points", limit=100, timezone="UTC", cursor=page["next_cursor"])
        assert {item["record_id"] for item in page["items"]}.isdisjoint(item["record_id"] for item in next_page["items"])
    print(json.dumps(results, ensure_ascii=False))
