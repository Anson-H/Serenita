"""Body record contracts, imports and authorization through real HTTP services."""

import io, json, zipfile
from uuid import uuid4
from datetime import date
import pytest
from member_support import accounts as accounts, account_id, create_member, grant
from backend.app.application.body_metric_import import parse_file
from backend.app.application.body_metric_demo import generate_records
from backend.app.application.body_metric_service import BodyMetricService
from backend.app.domain.body_metric_statistics import stats, select
from backend.app.schemas.body_metric import BodyRecord
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect


def base(member):
    return f"/api/members/{member}/body-metrics"


def measurement(metric="weight", value=68, **extra):
    return {
        "kind": "measurement",
        "metric": metric,
        "starts_at": "2026-09-07T08:00:00+08:00",
        "data": {"value": value, "unit": "kg"},
        **extra,
    }


def create(client, member, payload):
    r = client.post(base(member) + "/records", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def preview(client, member, records, name="data.json"):
    r = client.post(
        base(member) + "/imports/preview",
        headers={"Idempotency-Key": str(uuid4())},
        files={
            "file": (
                name,
                json.dumps(
                    {"format": "serenita-body-metrics", "records": records}
                ).encode(),
                "application/json",
            )
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def commit(client, member, job, selection=None):
    r = client.post(
        base(member) + f"/imports/{job['import_id']}/commit", json=selection or {}
    )
    assert r.status_code == 200, r.text
    r = client.get(base(member) + f"/imports/{job['import_id']}").json()
    assert r["state"] == "complete", r
    return r


def test_all_demo_data_and_template_round_trip(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    values = list(generate_records(days=90))
    parsed = [BodyRecord.model_validate(r) for r in values]
    assert len(parsed) > 5000
    job = commit(owner, member, preview(owner, member, values))
    assert job["inserted"] == len(values)
    assert job["categories"] and job["date_from"] and job["date_to"]
    statistics = owner.get(base(member) + "/statistics").json()
    assert len(statistics["series"]) == 31
    for fmt in ("json", "csv"):
        response = owner.get(base(member) + f"/template?format={fmt}")
        assert response.status_code == 200
        result = parse_file("template." + fmt, response.content)
        assert result["valid_count"] > 30 and not result["issues"], result
        assert {r["kind"] for r in result["records"]} == {
            "measurement",
            "meal",
            "sleep",
            "workout",
        }
        normalized = [
            {key: value for key, value in record.items() if key != "_source_payload"}
            for record in result["records"]
        ]
        if fmt == "json":
            expected = normalized
        else:
            assert normalized == expected


def test_import_identity_edit_reimport_overlap_delete_and_retry(accounts, monkeypatch):
    owner, *_ = accounts
    member = create_member(owner)
    service = BodyMetricService()
    actor = account_id("owner")
    record = measurement(external_id="stable-1", origin="standard", source="秤")
    job = preview(owner, member, [record])
    assert owner.get(base(member) + "/statistics").json()["total_records"] == 0
    commit(owner, member, job)
    saved = owner.get(base(member) + "/records").json()["items"][0]
    url = base(member) + "/records/" + saved["record_id"]
    assert (
        owner.patch(
            url, json={"data": {"value": 70}, "starts_at": "2026-09-08T09:00:00+08:00"}
        ).status_code
        == 200
    )
    assert (
        commit(owner, member, preview(owner, member, [record]))["inserted"] == 0
    )  # new preview reuses the existing source identity
    overlap = preview(
        owner,
        member,
        [record, measurement(external_id="stable-2", source="秤", origin="standard")],
    )
    assert overlap["duplicates"] == 1
    assert commit(owner, member, overlap)["inserted"] == 1
    assert owner.get(url).json()["data"]["value"] == 70
    assert (
        owner.get(base(member) + "/records?after=2026-09-08&before=2026-09-08").json()[
            "total"
        ]
        == 1
    )
    owner.delete(url)
    later = preview(owner, member, [record, measurement(external_id="stable-3")])
    commit(owner, member, later)
    assert owner.get(url).status_code == 404
    failed = preview(owner, member, [measurement(external_id="retry")])
    service.start_import(actor, member, failed["import_id"], {})
    from backend.app.repositories.body_metric_repository import BodyMetricRepository

    original = BodyMetricRepository.insert

    def broken(*args, **kwargs):
        raise ValueError("test interrupted write")

    with monkeypatch.context() as m:
        m.setattr(BodyMetricRepository, "insert", broken)
        service.run_import(actor, member, failed["import_id"])
    assert service.imports(actor, member, failed["import_id"])["state"] == "failed"
    service.start_import(actor, member, failed["import_id"], {})
    service.run_import(actor, member, failed["import_id"])
    assert service.imports(actor, member, failed["import_id"])["inserted"] == 1
    assert (
        owner.post(
            base(member) + f"/imports/{failed['import_id']}/commit",
            json={"categories": []},
        ).status_code
        == 400
    )


def test_meal_sleep_edits_recalculate_and_validate(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    meal = create(
        owner,
        member,
        {
            "kind": "meal",
            "starts_at": "2026-09-07T12:00:00+08:00",
            "data": {
                "meal_type": "lunch",
                "energy": 999,
                "foods": [
                    {
                        "food_id": "f",
                        "name": "米饭",
                        "amount": 100,
                        "energy": 120,
                        "carbohydrate": 26,
                        "protein": 3,
                        "fat": 0.5,
                    }
                ],
            },
        },
    )
    assert meal["data"]["energy"] == 120
    food = {
        **meal["data"]["foods"][0],
        "amount": 200,
        "energy": 240,
        "carbohydrate": 52,
        "protein": 6,
        "fat": 1,
    }
    updated = owner.patch(
        base(member) + "/records/" + meal["record_id"],
        json={
            "data": {"foods": [food], "meal_type": "dinner"},
            "starts_at": "2026-09-08T18:00:00+08:00",
        },
    ).json()
    assert updated["data"]["energy"] == 240 and updated["data"]["meal_type"] == "dinner"
    assert (
        owner.get(
            base(member) + "/statistics?after=2026-09-07&before=2026-09-07"
        ).json()["total_records"]
        == 0
    )
    sleep = create(
        owner,
        member,
        {
            "kind": "sleep",
            "starts_at": "2026-09-07T23:00:00+08:00",
            "ends_at": "2026-09-08T07:00:00+08:00",
            "precision": "interval",
            "data": {
                "score": 80,
                "score_max": 100,
                "stages": [
                    {
                        "stage_id": "a",
                        "stage": "light",
                        "starts_at": "2026-09-07T23:00:00+08:00",
                        "ends_at": "2026-09-08T01:00:00+08:00",
                    },
                    {
                        "stage_id": "b",
                        "stage": "deep",
                        "starts_at": "2026-09-08T01:00:00+08:00",
                        "ends_at": "2026-09-08T07:00:00+08:00",
                    },
                ],
            },
        },
    )
    assert sleep["data"]["duration_minutes"] == 480
    stages = sleep["data"]["stages"]
    stages[0]["stage"] = "awake"
    url = base(member) + "/records/" + sleep["record_id"]
    changed = owner.patch(url, json={"data": {"stages": stages}}).json()
    assert changed["data"]["duration_minutes"] == 360 and changed["data"]["score_stale"]
    stages[1]["starts_at"] = "2026-09-08T00:00:00+08:00"
    assert owner.patch(url, json={"data": {"stages": stages}}).status_code == 400
    assert owner.get(url).json()["data"]["duration_minutes"] == 360
    assert owner.patch(url, json={"timezone": "MadeUp/Zone"}).status_code == 400
    assert (
        owner.get(
            base(member) + "/records?after=2026-09-08&before=2026-09-08&category=sleep"
        ).json()["total"]
        == 1
    )


def test_interval_overlap_units_methods_sources_and_pressure():
    records = []

    def add(metric, value, unit, **kw):
        r = BodyRecord.model_validate(
            measurement(
                metric,
                value,
                data={"value": value, "unit": unit, **kw.pop("data", {})},
                **kw,
            )
        ).model_dump()
        r["record_id"] = str(len(records))
        records.append(r)

    add(
        "steps",
        120,
        "步",
        starts_at="2026-09-07T23:00:00+08:00",
        ends_at="2026-09-08T01:00:00+08:00",
        precision="interval",
    )
    add(
        "steps",
        30,
        "步",
        starts_at="2026-09-08T00:30:00+08:00",
        ends_at="2026-09-08T01:00:00+08:00",
        precision="interval",
    )
    add("steps", 200, "步", source="other")
    add("hrv", 40, "ms", data={"method": "SDNN"})
    add("hrv", 60, "ms", data={"method": "RMSSD"})
    add("blood_pressure", 120, "mmHg", data={"secondary_value": 80})
    add("blood_pressure", 130, "mmHg", data={"secondary_value": 90})
    add("blood_glucose", 180.182, "mg/dL")
    values = stats(records)
    step = next(
        s for s in values if s["metric"] == "steps" and s["source"] == "手工记录"
    )
    assert (
        step["total"] == 120
        and [b["value"] for b in step["buckets"]] == [60, 60]
        and step["omitted_overlaps"] == 1
    )
    assert step["count"] == 2 and [p["value"] for p in step["points"]] == [120, 30]
    assert all(not p["allocated"] for p in step["points"])
    assert len([s for s in values if s["metric"] == "hrv"]) == 2
    bp = next(s for s in values if s["metric"] == "blood_pressure")
    assert bp["mean"] == 125 and bp["secondary_mean"] == 85
    assert next(s for s in values if s["metric"] == "blood_glucose")["mean"] == 10
    day = stats(
        select(records, "2026-09-08", "2026-09-08"),
        after="2026-09-08",
        before="2026-09-08",
    )
    assert day[0]["total"] == 60


def test_member_permissions_files_and_deletion(accounts):
    owner, reader, editor = accounts
    member = create_member(owner)
    other = create_member(owner)
    grant(owner, member, "reader", "read")
    grant(owner, member, "editor", "edit")
    record = create(
        owner,
        member,
        {
            "kind": "meal",
            "starts_at": "2026-09-07T12:00:00+08:00",
            "data": {"energy": 100},
        },
    )
    url = base(member) + "/records/" + record["record_id"]
    image = b"\x89PNG\r\n\x1a\n" + b"fixture"
    attached = owner.post(
        url + "/files", files={"file": ("demo.png", image, "image/png")}
    ).json()
    file_id = attached["files"][0]["file_id"]
    assert reader.get(url + "/files/" + file_id).content == image
    for client in (reader,):
        assert client.patch(url, json={"data": {"energy": 200}}).status_code == 403
        assert (
            client.post(
                url + "/files", files={"file": ("d.png", image, "image/png")}
            ).status_code
            == 403
        )
        assert (
            client.post(
                base(member) + "/imports/preview",
                headers={"Idempotency-Key": str(uuid4())},
                files={"file": ("x.json", b"{}")},
            ).status_code
            == 403
        )
    assert owner.get(base(other) + "/records/" + record["record_id"]).status_code == 404
    assert editor.get(base(other) + "/catalog").status_code == 403
    assert editor.patch(url, json={"data": {"energy": 110}}).status_code == 200
    owner.delete("/api/members/" + member)
    with connect(app_paths().body_metrics_db(account_id("owner"))) as db:
        assert db.execute("SELECT count(*) FROM body_records").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM body_files").fetchone()[0] == 0


def test_apple_zip_fields_and_unknown_and_malformed():
    attrs = 'sourceName="Apple Watch" startDate="2026-09-07 08:00:00 +0800" endDate="2026-09-07 08:00:00 +0800"'
    xml = (
        "<HealthData>"
        + "".join(
            f'<Record {attrs} type="HKQuantityTypeIdentifier{t}" unit="{u}" value="{v}"/>'
            for t, u, v in [
                ("BodyMassIndex", "count", 22),
                ("BodyFatPercentage", "%", 0.2),
                ("OxygenSaturation", "%", 0.98),
                ("HeartRateVariabilitySDNN", "ms", 40),
                ("BloodPressureSystolic", "mmHg", 120),
                ("BloodPressureDiastolic", "mmHg", 80),
                ("Unknown", "x", 5),
            ]
        )
        + "</HealthData>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("apple_health_export/export.xml", xml)
    result = parse_file("health.zip", buffer.getvalue())
    assert not result["issues"] and result["valid_count"] == 5
    assert result["unsupported"]["HKQuantityTypeIdentifierUnknown"] == 1
    assert (
        next(r for r in result["records"] if r["metric"] == "body_fat")["data"]["value"]
        == 20
    )
    with pytest.raises(ValueError):
        parse_file(
            "evil.xml",
            b'<!DOCTYPE x [<!ENTITY a SYSTEM "file:///etc/passwd">]><HealthData/>',
        )


def test_plugin_tools_obey_member_context_and_real_writes(accounts):
    from types import SimpleNamespace
    from backend.app.plugins.body_metric.registry import build_tools, build_skills
    from backend.app.plugins.body_metric.tools.record_tools import DESCRIPTIONS
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    from backend.app.core.errors import SerenitaError

    owner, reader, editor = accounts
    member = create_member(owner)
    grant(owner, member, "reader", "read")
    grant(owner, member, "editor", "edit")
    context = PluginRuntimeContext(
        account_id=account_id("editor"), member_id=member, event_recorder=lambda _: None
    )
    tools = {t.name: t for t in build_tools(runtime_context=context)}
    assert set(tools) == set(DESCRIPTIONS) and build_skills()[0].name == "body-metrics"
    assert (
        tools["create_body_record"].input_schema["properties"]["record"]["type"]
        == "object"
    )
    saved = (
        tools["create_body_record"]
        .run({"record": measurement(), "request_id": "one"})
        .output
    )
    assert saved["path"].endswith("?record=" + saved["record_id"])
    assert (
        tools["read_body_record"]
        .run({"record_id": saved["record_id"]})
        .output["data"]["value"]
        == 68
    )
    tools["update_body_record"].run(
        {"record_id": saved["record_id"], "changes": {"data": {"value": 69}}}
    )
    assert tools["read_body_statistics"].run({}).output["series"][0]["latest"] == 69
    assert "data" not in tools["read_body_record_catalog"].run({}).output["items"][0]
    with pytest.raises(PermissionError):
        tools["read_body_record"].bind_runtime_arguments(
            {},
            context=SimpleNamespace(account_id=context.account_id, member_id="other"),
            observations=[],
        )
    readonly = {
        t.name: t
        for t in build_tools(
            runtime_context=PluginRuntimeContext(
                account_id=account_id("reader"),
                member_id=member,
                event_recorder=lambda _: None,
            )
        )
    }
    with pytest.raises(SerenitaError):
        readonly["delete_body_record"].run({"record_id": saved["record_id"]})
    assert (
        tools["delete_body_record"]
        .run({"record_id": saved["record_id"]})
        .output["deleted"]
    )


def test_partial_import_write_failure_is_atomic(accounts, monkeypatch):
    from backend.app.repositories.body_metric_repository import BodyMetricRepository

    owner, *_ = accounts
    member = create_member(owner)
    service = BodyMetricService()
    actor = account_id("owner")
    job = preview(
        owner, member, [measurement(external_id="a"), measurement(external_id="b")]
    )
    service.start_import(actor, member, job["import_id"], {})
    insert = BodyMetricRepository.insert
    calls = []

    def fail_second(self, *args, **kw):
        calls.append(1)
        if len(calls) == 2:
            raise ValueError("failure after first insert")
        return insert(self, *args, **kw)

    with monkeypatch.context() as m:
        m.setattr(BodyMetricRepository, "insert", fail_second)
        service.run_import(actor, member, job["import_id"])
    assert service.query(actor, member)["total"] == 0
    service.start_import(actor, member, job["import_id"], {})
    service.run_import(actor, member, job["import_id"])
    assert service.query(actor, member)["total"] == 2


def test_apple_sleep_stages_scores_and_stable_identity():
    def xml(value=68):
        def record(typ, value, start, end, unit=""):
            return f'<Record type="{typ}" sourceName="Watch" startDate="{start} +0800" endDate="{end} +0800" unit="{unit}" value="{value}"/>'

        return (
            "<HealthData>"
            + record(
                "HKQuantityTypeIdentifierBodyMass",
                value,
                "2026-09-08 08:00:00",
                "2026-09-08 08:00:00",
                "kg",
            )
            + "".join(
                record("HKCategoryTypeIdentifierSleepAnalysis", v, a, b)
                for v, a, b in [
                    (
                        "HKCategoryValueSleepAnalysisInBed",
                        "2026-09-07 23:00:00",
                        "2026-09-08 07:00:00",
                    ),
                    (
                        "HKCategoryValueSleepAnalysisAsleepCore",
                        "2026-09-07 23:00:00",
                        "2026-09-08 03:00:00",
                    ),
                    (
                        "HKCategoryValueSleepAnalysisAsleepDeep",
                        "2026-09-08 03:00:00",
                        "2026-09-08 07:00:00",
                    ),
                ]
            )
            + "</HealthData>"
        ).encode()

    result = parse_file("export.xml", xml())
    assert not result["issues"]
    sleep = next(r for r in result["records"] if r["kind"] == "sleep")
    assert (
        sleep["data"]["duration_minutes"] == 480
        and len(sleep["data"]["stages"]) == 2
        and sleep["data"]["score"] is None
    )
    assert (
        result["records"][0]["external_id"]
        == parse_file("export.xml", xml(69))["records"][0]["external_id"]
    )


def test_sleep_only_import_defaults_to_waking_date(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    payload = {
        "kind": "sleep",
        "starts_at": "2026-09-07T23:00:00+08:00",
        "ends_at": "2026-09-08T07:00:00+08:00",
        "precision": "interval",
        "data": {"duration_minutes": 480},
    }
    job = preview(owner, member, [payload])
    assert job["date_from"] == job["date_to"] == "2026-09-08"
    result = commit(
        owner, member, job, {"after": job["date_from"], "before": job["date_to"]}
    )
    assert result["inserted"] == 1


def test_batch_deletion_retains_independent_shared_and_changed_records(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    manual = measurement(external_id="manual", source="秤", origin="standard")
    independent = create(owner, member, manual)
    entries = [
        manual,
        measurement(external_id="shared"),
        measurement(external_id="changed"),
        measurement(external_id="untouched"),
    ]
    first = commit(owner, member, preview(owner, member, entries))
    second = commit(owner, member, preview(owner, member, [entries[1]]))
    records = {
        r.get("external_id"): r
        for r in owner.get(base(member) + "/records").json()["items"]
    }
    changed = records["changed"]
    assert (
        owner.patch(
            base(member) + "/records/" + changed["record_id"],
            json={"notes": "修正了备注"},
        ).json()["import_managed"]
        is False
    )
    untouched = records["untouched"]
    assert (
        owner.patch(
            base(member) + "/records/" + untouched["record_id"],
            json={"data": {"value": 68}},
        ).json()["import_managed"]
        is True
    )
    outcome = owner.delete(base(member) + "/imports/" + first["import_id"]).json()
    assert outcome == {"deleted": True, "records_deleted": 1, "records_retained": 3}
    assert (
        owner.get(base(member) + "/records/" + independent["record_id"]).status_code
        == 200
    )
    outcome = owner.delete(base(member) + "/imports/" + second["import_id"]).json()
    assert outcome["records_deleted"] == 1
    assert (
        owner.get(base(member) + "/records/" + changed["record_id"]).status_code == 200
    )
    # Retained identities have no exclusion; a new batch may still reference them.
    assert (
        commit(owner, member, preview(owner, member, [manual]))["selected_count"] == 1
    )


def test_partial_same_file_new_upload_and_idempotent_preview(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    records = [
        measurement(external_id="one"),
        measurement(external_id="two", starts_at="2026-09-08T08:00:00+08:00"),
    ]
    content = json.dumps(
        {"format": "serenita-body-metrics", "records": records}
    ).encode()
    headers = {"Idempotency-Key": "upload-attempt-1"}

    def upload(key=headers):
        response = owner.post(
            base(member) + "/imports/preview",
            headers=key,
            files={"file": ("same.json", content, "application/json")},
        )
        assert response.status_code == 200, response.text
        return response.json()

    first = upload()
    assert upload()["import_id"] == first["import_id"]
    commit(owner, member, first, {"before": "2026-09-07"})
    next_job = upload({"Idempotency-Key": "upload-attempt-2"})
    assert next_job["import_id"] != first["import_id"] and next_job["duplicates"] == 1
    assert commit(owner, member, next_job, {"after": "2026-09-08"})["inserted"] == 1
    assert owner.get(base(member) + "/records").json()["total"] == 2


def test_utc_order_local_boundaries_stale_scores_and_bounded_series(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    create(
        owner,
        member,
        measurement(external_id="earlier", starts_at="2026-09-07T10:30:00+09:00"),
    )
    later = create(
        owner,
        member,
        measurement(external_id="later", starts_at="2026-09-06T23:00:00-04:00"),
    )
    page = owner.get(
        base(member)
        + "/records?timezone=UTC&after=2026-09-07&before=2026-09-07&limit=1"
    ).json()
    assert page["total"] == 2 and page["items"][0]["record_id"] == later["record_id"]
    assert later["starts_at"] == "2026-09-07T03:00:00.000000+00:00"
    sleep = create(
        owner,
        member,
        {
            "kind": "sleep",
            "starts_at": "2026-09-07T23:00:00+08:00",
            "ends_at": "2026-09-08T07:00:00+08:00",
            "precision": "interval",
            "data": {"score": 80, "score_max": 100, "duration_minutes": 480},
        },
    )
    owner.patch(
        base(member) + "/records/" + sleep["record_id"],
        json={"ends_at": "2026-09-08T08:00:00+08:00"},
    )
    summary = owner.get(base(member) + "/statistics?timezone=UTC").json()
    assert summary["excluded_stale_scores"] == 1
    assert not any(s["metric"] == "sleep_score" for s in summary["series"])
    assert all("points" not in s and "buckets" not in s for s in summary["series"])
    weight = next(s for s in summary["series"] if s["metric"] == "weight")
    url = (
        base(member)
        + "/statistics/series/"
        + weight["series_id"]
        + "?timezone=UTC&view=points&limit=1"
    )
    first = owner.get(url).json()
    second = owner.get(url + "&cursor=" + first["next_cursor"]).json()
    assert first["total"] == 2 and len(first["items"]) == len(second["items"]) == 1
    assert (
        second["next_cursor"] is None
        and first["items"][0]["record_id"] != second["items"][0]["record_id"]
    )


def test_import_preserves_original_offset_units_and_raw_statistical_points(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    original = measurement(
        "blood_glucose",
        180.182,
        starts_at="2026-09-07T23:30:00-07:00",
        data={"value": 180.182, "unit": "mg/dL"},
    )
    commit(owner, member, preview(owner, member, [original]))
    duplicate = preview(owner, member, [original])
    assert duplicate["duplicates"] == 1 and duplicate["new_count"] == 0
    assert commit(owner, member, duplicate)["inserted"] == 0
    saved = owner.get(base(member) + "/records").json()["items"][0]
    assert saved["starts_at"] == "2026-09-08T06:30:00.000000+00:00"
    assert saved["data"]["value"] == 10
    with connect(app_paths().body_metrics_db(account_id("owner"))) as db:
        assert (
            json.loads(
                db.execute(
                    "SELECT source_payload FROM body_records WHERE record_id=?",
                    (saved["record_id"],),
                ).fetchone()[0]
            )
            == original
        )
    outside = create(owner, member, measurement(starts_at="2026-01-01T00:00:00Z"))
    result = owner.get(
        base(member)
        + "/statistics?after=2026-09-07&before=2026-09-07&timezone=America/Los_Angeles"
    ).json()
    assert result["total_records"] == 1
    assert result["coverage_dates"] == {
        "first": "2026-09-07",
        "last": "2026-09-07",
        "recorded_days": 1,
    }
    assert result["coverage_from"] == saved["starts_at"]
    assert result["coverage_from"] != outside["starts_at"]


def test_daily_allocation_uses_elapsed_hours_across_dst():
    record = BodyRecord.model_validate(
        measurement(
            "steps",
            710,
            data={"value": 710, "unit": "步"},
            starts_at="2026-03-07T00:00:00-05:00",
            ends_at="2026-03-10T00:00:00-04:00",
            precision="interval",
        )
    ).model_dump()
    record["record_id"] = "dst"
    series = stats([record], timezone="America/New_York")[0]
    assert [item["value"] for item in series["buckets"]] == [240, 230, 240]
    assert series["total"] == 710 and series["count"] == 1
    assert series["points"][0]["value"] == 710


def test_body_catalog_and_series_read_all_internal_pages(accounts):
    from datetime import datetime, timedelta, timezone
    from backend.app.plugins.body_metric.registry import build_tools
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    from backend.app.agent_runtime.tools.parameters import validate_parameters
    owner, *_ = accounts
    member = create_member(owner)
    service = BodyMetricService()
    for index in range(101):
        service.create(account_id("owner"), member, measurement(
            value=60 + index / 10,
            starts_at=(datetime(2026, 1, 1, 8, tzinfo=timezone.utc) + timedelta(days=index)).isoformat(),
        ), str(uuid4()))
    tools = {tool.name: tool for tool in build_tools(runtime_context=PluginRuntimeContext(
        account_id=account_id("owner"), member_id=member, event_recorder=lambda _: None,
    ))}
    def pages(result):
        values = []
        while True:
            values.extend(result.output["items"])
            if result.next_page is None:
                assert result.output["pagination"]["complete"]
                return values
            assert not result.output["pagination"]["complete"]
            result = result.next_page()
    catalog = tools["read_body_record_catalog"]
    records = pages(catalog.run({}))
    assert len(records) == len({item["record_id"] for item in records}) == 101
    statistics = tools["read_body_statistics"]
    series_id = statistics.run({}).output["series"][0]["series_id"]
    for view in ("buckets", "points"):
        assert len(pages(statistics.run({"series_id": series_id, "view": view}))) == 101
    for tool in (catalog, statistics):
        for argument in ("cursor", "offset", "limit"):
            with pytest.raises(ValueError):
                validate_parameters({argument: 1}, tool.input_schema, label=tool.name)
