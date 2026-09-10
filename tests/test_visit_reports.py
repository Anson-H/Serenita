from copy import deepcopy

import pytest
from pydantic import ValidationError
from member_support import accounts, account_id, create_member, grant
from backend.app.application.report_service import ReportService
from backend.app.application.favorite_service import _report_snapshot
from backend.app.core.errors import SerenitaError
from backend.app.schemas.report import ParsedReport, REPORT_STRUCTURES
from backend.app.storage.sqlite import connect
from backend.app.storage.paths import app_paths


def visit(kind, **fields):
    key = "outpatient_report" if kind == "门诊病历" else "emergency_report"
    return {"report_type": kind, "report_name": "就诊记录", "report_time": "2026-09-01T12:30:00+08:00", key: fields}


@pytest.mark.parametrize("kind,key", [("门诊病历", "outpatient_report"), ("急诊病历", "emergency_report")])
def test_visit_api_complete_fields_edits_permissions_and_delete(accounts, kind, key):
    owner, reader, editor = accounts
    member = create_member(owner)
    other = create_member(owner)
    grant(owner, member, "reader", "read")
    grant(owner, member, "editor", "edit")
    fields = {name: f"原件：{field.title}不详" for name, field in REPORT_STRUCTURES[kind][1].model_fields.items()}
    created = owner.post(f"/api/members/{member}/reports", json=visit(kind, **fields))
    assert created.status_code == 201, created.text
    report = created.json()
    rid = report["report_id"]
    url = f"/api/members/{member}/reports/{rid}"
    for name, value in fields.items(): assert report[key][name] == value
    assert owner.get(f"/api/members/{other}/reports/{rid}").status_code == 404
    assert reader.get(url).status_code == 200
    assert reader.patch(url + "/fields", json={"field": "diagnosis", "value": "x"}).status_code == 403
    assert len(owner.get(f"/api/members/{member}/reports", params={"report_type": kind}).json()["reports"]) == 1
    service = ReportService.for_member(account_id("owner"), member)
    service.repository.save_report_analysis(member, rid, "已有解读结果")
    for name in fields:
        changed = editor.patch(url + "/fields", json={"field": name, "value": f"修正：{name}"})
        assert changed.status_code == 200, changed.text
        assert changed.json()[key][name] == f"修正：{name}"
        assert changed.json()["analysis_outdated"] is True
    assert editor.patch(url + "/fields", json={"field": "chief_complaint", "value": None}).json()[key]["chief_complaint"] is None
    markdown = _report_snapshot(owner.get(url).json())
    assert "修正：diagnosis" in markdown
    if kind == "急诊病历":
        assert "修正：discharge_diagnosis" in markdown and "修正：discharge_instructions" in markdown
    assert owner.delete(f"/api/members/{member}").status_code == 200
    with connect(app_paths().reports_db(account_id("owner"))) as db:
        assert db.execute(f"SELECT 1 FROM {key} WHERE report_id = ?", (rid,)).fetchone() is None


@pytest.mark.parametrize("kind,key", [("门诊病历", "outpatient_report"), ("急诊病历", "emergency_report")])
def test_visit_import_merge_reclassify_and_sources(accounts, kind, key):
    owner, _, _ = accounts
    member = create_member(owner)
    service = ReportService.for_member(account_id("owner"), member)
    def parse(payload, message):
        return payload, dict(sources=[{"source_type": "conversation_text"}], source_text="原件：主诉腹痛，诊断待查。其余未记载。", session_id="visit-session", source_message_id=message, visible_attachments={}, authorized_report_sources={})
    parsed, source = parse(visit(kind, chief_complaint="腹痛", diagnosis="待查"), "first")
    report = service.create_report_from_parsed(member, report=parsed, **source)
    rid = report["report_id"]
    detail = service.repository.get_report_detail(member, rid)
    assert detail[key]["physical_examination"] is None
    assert len(detail["sources"]) == 1
    sources = deepcopy(detail["sources"])
    service.repository.save_report_analysis(member, rid, "已有解读结果")
    enriched, second_source = parse(visit(kind, chief_complaint="腹痛", diagnosis="待查", treatment_plan="复诊"), "second")
    service.merge_parsed_report(member, report=enriched, target_report_id=rid, **second_source)
    detail = service.repository.get_report_detail(member, rid)
    assert detail[key]["treatment_plan"] == "复诊"
    assert detail["analysis_outdated"] is True
    conflict = deepcopy(enriched)
    conflict[key]["diagnosis"] = "另一诊断"
    conflict[key]["additional_content"] = "不得部分保存"
    with pytest.raises(Exception):
        service.merge_parsed_report(member, report=conflict, target_report_id=rid, **second_source)
    assert service.repository.get_report_detail(member, rid)[key]["additional_content"] is None
    opposite = "急诊病历" if kind == "门诊病历" else "门诊病历"
    opposite_key = "emergency_report" if key == "outpatient_report" else "outpatient_report"
    new_payload = ParsedReport.model_validate(visit(opposite, diagnosis="待查")).model_dump()
    reclassified = service.repository.reclassify_report(member, rid, new_payload)
    assert reclassified["report_id"] == rid
    assert reclassified["report_time"] == detail["report_time"]
    assert reclassified[key] is None
    assert reclassified[opposite_key]["diagnosis"] == "待查"
    assert reclassified["sources"] == detail["sources"]
    assert sources[0]["resource_id"] in {item["resource_id"] for item in reclassified["sources"]}
    service.delete_report(member, rid)
    assert service.repository.get_report_detail(member, rid) is None


def test_visit_payload_missing_structure_and_wrong_type():
    with pytest.raises(ValidationError): ParsedReport.model_validate({"report_type": "门诊病历", "report_name": "门诊", "report_time": "2026-09-01"})
    with pytest.raises(ValidationError): ParsedReport.model_validate({**visit("门诊病历"), "emergency_report": {}})
    with pytest.raises(ValidationError): ParsedReport.model_validate(visit("门诊病历", discharge_instructions="不属于门诊字段"))
    assert ParsedReport.model_validate(visit("急诊病历")).emergency_report.discharge_diagnosis is None
