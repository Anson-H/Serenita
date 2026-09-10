from tests.report_support import report_payload
from backend.app.api.errors import error_http_status
from member_support import account_id as account_id_for, member_access
import hashlib
import pytest
from backend.app.core.errors import SerenitaError
from backend.app.application.report_service import ReportService
from backend.app.application.report_validation import normalize_analysis_content, semantic_lab_category
from backend.app.repositories.report_repository import ReportRepository
from backend.app.core.report_errors import ReportImportWriteConflictError
from backend.app.storage.paths import AppPaths




@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    paths = AppPaths(tmp_path)
    return ReportService(
        scope=member_access("demo"),
        repository=ReportRepository(account_id_for("demo"), paths),
        paths=paths,
    )


def write_arguments(*, text="医疗报告文本", report=None, message_id="message"):
    return dict(report=report or report_payload(),
                sources=[{"source_type": "conversation_text"}],
                source_text=text, session_id="session", source_message_id=message_id,
                visible_attachments={}, authorized_report_sources={})


def create(service, **arguments):
    return service.create_report_from_parsed(service.scope.member_id, **write_arguments(**arguments))


@pytest.mark.parametrize("flag_text", ["未标记", "正常", "异常", "偏高", "偏低"])
def test_lab_flag_uses_text_enum(service, flag_text):
    created = create(service)
    updated = service.update_report_field(
        service.scope.member_id,
        created["report_id"],
        field="lab_flag",
        item_id="item-alt",
        value=flag_text,
    )
    assert updated["lab_test_results"][0]["flag_text"] == flag_text


def test_lab_flag_rejects_arrow_symbols(service):
    created = create(service)
    with pytest.raises(SerenitaError) as exc_info:
        service.update_report_field(
            service.scope.member_id,
            created["report_id"],
            field="lab_flag",
            item_id="item-alt",
            value="↑",
        )
    assert error_http_status(exc_info.value) == 400
    assert "未标记、正常、异常、偏高或偏低" in str(exc_info.value.detail)


def test_missing_lab_flag_defaults_to_unmarked(service):
    payload = report_payload()
    payload["lab_test_results"][0].pop("flag_text")
    created = create(service, report=payload)
    detail = service.get_report(service.scope.member_id, created["report_id"])
    assert detail["lab_test_results"][0]["flag_text"] == "未标记"


def test_create_validates_and_persists_exact_bound_text(service):
    text = "2026-08-08 肝功能 ALT 65 U/L"
    created = create(service, text=text)
    detail = service.get_report(service.scope.member_id, created["report_id"])
    source = detail["sources"][0]
    path, _, _ = service.source_download(service.scope.member_id, created["report_id"], source["resource_id"])
    assert path.read_text() == text
    assert service.resolve_report_source(service.scope.member_id, created["report_id"], source["resource_id"])["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert detail["report_name"] == "肝功能"


def test_writes_share_sources_and_reject_duplicate_references(service):
    first = create(service, text="同一消息含两份医疗报告")
    second = create(service, text="同一消息含两份医疗报告", report=report_payload(report_type="检查报告"))
    details = [service.get_report(service.scope.member_id, value["report_id"]) for value in (first, second)]
    assert details[0]["sources"][0]["resource_id"] == details[1]["sources"][0]["resource_id"]
    arguments = write_arguments(text="重复")
    arguments["sources"] *= 2
    with pytest.raises(ValueError, match="不能重复绑定"):
        service.create_report_from_parsed(service.scope.member_id, **arguments)
    assert service.list_reports(service.scope.member_id)["total"] == 2


def test_write_rejects_unauthorized_and_mixed_category_sources(service):
    arguments = write_arguments()
    arguments["sources"] = [{"source_type": "conversation_attachment", "resource_id": "forged"}]
    with pytest.raises(PermissionError, match="当前分支可见消息"):
        service.create_report_from_parsed(service.scope.member_id, **arguments)
    mixed = report_payload()
    mixed["lab_test_results"].append({**mixed["lab_test_results"][0], "item_id": "item-creatinine", "item_name_zh": "肌酐", "category_name": "肾功能"})
    with pytest.raises(ValueError, match="只能包含一个"):
        create(service, report=mixed)
    assert service.list_reports(service.scope.member_id)["total"] == 0
    assert not list(service.paths.report_attachments_dir(service.account_id).glob("*"))


def test_validation_requires_lab_name_to_match_single_category(service):
    payload = report_payload()
    payload["report_name"] = "生化医疗报告"
    with pytest.raises(ValueError, match="完全一致"):
        create(service, report=payload)


def test_validation_rejects_duplicate_item_id_in_one_report(service):
    payload = report_payload()
    payload["lab_test_results"].append(
        {
            **payload["lab_test_results"][0],
            "item_name_zh": "重复展示名称不影响身份校验",
        }
    )
    with pytest.raises(ValueError, match="不能重复包含同一个 item_id"):
        create(service, report=payload)


def test_invalid_write_preserves_dictionary_reports_and_files(service):
    create(service, text="既有医疗报告", message_id="existing")
    dictionary_before = service.repository.lab_dictionary(service.scope.member_id)
    reports_before = service.list_reports(service.scope.member_id)
    files_before = set(service.paths.report_attachments_dir(service.account_id).glob("*"))
    payload = report_payload()
    payload["report_name"] = "名称不匹配"
    with pytest.raises(ValueError, match="完全一致"):
        create(service, text="无效内容", report=payload, message_id="invalid")
    assert service.repository.lab_dictionary(service.scope.member_id) == dictionary_before
    assert service.list_reports(service.scope.member_id) == reports_before
    assert set(service.paths.report_attachments_dir(service.account_id).glob("*")) == files_before


def test_create_persists_all_sources_in_order_with_first_primary(service, tmp_path):
    attachment = tmp_path / 'report.jpg'
    content = b'\xff\xd8\xffreport'
    attachment.write_bytes(content)
    text = '文本与图片共同构成一份医疗报告'
    result = service.create_report_from_parsed(service.scope.member_id, source_text=text, session_id='session', source_message_id='message', visible_attachments={'resource-one': {'resource_id': 'resource-one', 'path': str(attachment), 'original_filename': 'report.jpg', 'mime_type': 'image/jpeg', 'sha256': hashlib.sha256(content).hexdigest()}}, authorized_report_sources={}, sources=[{'source_type': 'conversation_text'}, {'source_type': 'conversation_attachment', 'resource_id': 'resource-one'}], report=report_payload())
    sources = service.get_report(service.scope.member_id, result['report_id'])['sources']
    assert len(sources) == 2
    assert sources[0]['is_primary'] is True
    assert sources[0]['mime_type'] == 'text/plain'
    assert sources[1]['is_primary'] is False
    image_resource_id = sources[1]['resource_id']
    stored_image = service.repository.source_file(service.scope.member_id, image_resource_id)
    assert stored_image is not None
    assert stored_image['relative_path'] == f'reports/attachments/{image_resource_id}.jpg'
    stored_path = service.paths.account_root(service.account_id) / stored_image['relative_path']
    assert stored_path.resolve() != attachment.resolve()
    assert stored_path.read_bytes() == content


def test_same_conversation_resource_id_in_different_sessions_stays_distinct(service, tmp_path):
    resource_ids = []
    for ordinal, session_id in enumerate(("session-one", "session-two"), start=1):
        attachment = tmp_path / f"conversation-{ordinal}.jpg"
        content = b"\xff\xd8\xff" + f"report-{ordinal}".encode()
        attachment.write_bytes(content)
        arguments = write_arguments()
        arguments.update(session_id=session_id, sources=[{"source_type": "conversation_attachment", "resource_id": "same-name.jpg"}],
            visible_attachments={"same-name.jpg": {"path": str(attachment), "original_filename": "same-name.jpg", "mime_type": "image/jpeg", "sha256": hashlib.sha256(content).hexdigest()}})
        created = service.create_report_from_parsed(service.scope.member_id, **arguments)
        resource_ids.append(service.get_report(service.scope.member_id, created["report_id"])["sources"][0]["resource_id"])
    assert all(value.startswith("RESOURCE-") for value in resource_ids)
    assert len(set(resource_ids)) == 2


def test_link_sources_preserves_primary(service):
    created = create(service, text="首个来源", message_id="one")
    report_id = created["report_id"]
    before = service.get_report(service.scope.member_id, report_id)
    for text, message_id in (("第二来源", "two"), ("第三来源", "three")):
        service.link_parsed_report_sources(service.scope.member_id, target_report_id=report_id, **write_arguments(text=text, message_id=message_id))
    after = service.get_report(service.scope.member_id, report_id)
    assert len(after["sources"]) == 3
    assert after["sources"][0]["resource_id"] == before["sources"][0]["resource_id"]
    assert after["sources"][0]["is_primary"] is True
    assert after["updated_at"] > before["updated_at"]


def test_all_import_write_tools_proceed_without_corpus_observation(service):
    arguments = write_arguments(text='创建来源', message_id='one')
    created = service.create_report_from_parsed(service.scope.member_id, **arguments)
    report_id = created['report_id']
    arguments = write_arguments(text='关联来源', message_id='two')
    linked = service.link_parsed_report_sources(service.scope.member_id, target_report_id=report_id, **arguments)
    assert linked['report_id'] == report_id
    merge_payload = report_payload()
    merge_payload['lab_test_results'].append({'item_id': 'item-ast', 'item_name_zh': '天冬氨酸氨基转移酶', 'aliases': ['谷草转氨酶'], 'category_name': '肝功能', 'result_text': '30 U/L', 'reference_text': '15-40 U/L', 'flag_text': '正常'})
    arguments = write_arguments(text='合并来源', report=merge_payload, message_id='three')
    merged = service.merge_parsed_report(service.scope.member_id, target_report_id=report_id, **arguments)
    assert merged['report_id'] == report_id
    assert merged['changed'] is True
    assert merged['added_item_ids'] == ['item-ast']


def test_conflicting_merge_does_not_partially_write(service):
    created = create(service, text='基础', message_id='base')
    report_id = created['report_id']
    arguments = write_arguments(text='冲突', report=report_payload(result='99 U/L'), message_id='conflict')
    before = service.get_report(service.scope.member_id, report_id)
    with pytest.raises(ReportImportWriteConflictError):
        service.merge_parsed_report(service.scope.member_id, target_report_id=report_id, **arguments)
    assert service.get_report(service.scope.member_id, report_id) == before


def test_evidence_sources_authorize_reclassification_without_time_change(service):
    created = create(service)
    report_id = created['report_id']
    before = service.get_report(service.scope.member_id, report_id)
    evidence = service.query_evidence(service.scope.member_id, report_ids=[report_id], fields=['sources'])
    source = evidence['reports'][0]['sources'][0]
    target = report_payload(report_type='检查报告')
    target['report_time'] = '2030-01-01T00:00:00+00:00'
    updated = service.reclassify_report(service.scope.member_id, report_id, source_text='', session_id='session', source_message_id='message', visible_attachments={}, authorized_report_sources={f"read-one\x00{report_id}\x00{source['resource_id']}": source}, sources=[{'source_type': 'report_source', 'read_call_id': 'read-one', 'report_id': report_id, 'resource_id': source['resource_id']}], report=target)
    assert updated['report_type'] == '检查报告'
    assert updated['report_time'] == before['report_time']
    assert [item['resource_id'] for item in updated['sources']] == [item['resource_id'] for item in before['sources']]


def test_analysis_write_persists_markdown_and_binding(service):
    created = create(service, report=report_payload(report_type="检查报告"))
    report_id = created["report_id"]

    updated = service.update_report_field(
        service.scope.member_id,
        report_id,
        field="exam_findings",
        value="复核后仍未见明显异常",
    )
    assert updated["examination_report"]["exam_findings"] == "复核后仍未见明显异常"

    stored = service.write_report_analysis(
        service.scope.member_id,
        report_id=report_id,
        analysis_content="## 需注意信号\n\n无。\n\n## 近期关注重点\n\n按需复查。",
    )
    assert stored["analysis_content"].endswith("按需复查。")
    assert set(stored) == {
        "report_id",
        "analysis_content",
        "analysis_updated_at",
        "analysis_outdated",
        "conversation_binding",
    }


def test_report_edit_only_invalidates_its_own_analysis(service):
    first = create(
        service,
        text="第一份检查报告",
        message_id="first",
        report=report_payload(report_type="检查报告"),
    )
    second = create(
        service,
        text="第二份检查报告",
        message_id="second",
        report=report_payload(report_type="检查报告"),
    )
    for report_id in (first["report_id"], second["report_id"]):
        service.write_report_analysis(
            service.scope.member_id,
            report_id=report_id,
            analysis_content="当前医疗报告解读。",
        )

    service.update_report_field(
        service.scope.member_id,
        first["report_id"],
        field="exam_findings",
        value="复核后更新检查表现",
    )

    assert service.get_report(service.scope.member_id, first["report_id"])["analysis_outdated"] is True
    assert service.get_report(service.scope.member_id, second["report_id"])["analysis_outdated"] is False


def test_update_report_fields_updates_multiple_fields_in_one_transaction(service):
    created = create(service, report=report_payload(report_type="检查报告"))
    report_id = created["report_id"]
    service.write_report_analysis(
        service.scope.member_id,
        report_id=report_id,
        analysis_content="当前医疗报告解读。",
    )

    updated = service.update_report_fields(
        service.scope.member_id,
        report_id,
        updates=[
            {"field": "clinical_diagnosis", "value": "复核诊断"},
            {"field": "exam_findings", "value": "复核后检查所见"},
        ],
    )

    assert updated["examination_report"]["clinical_diagnosis"] == "复核诊断"
    assert updated["examination_report"]["exam_findings"] == "复核后检查所见"
    assert updated["analysis_outdated"] is True


def test_update_report_fields_rolls_back_when_any_change_is_invalid(service):
    created = create(service, report=report_payload(report_type="检查报告"))
    report_id = created["report_id"]
    original_findings = service.get_report(service.scope.member_id, report_id)["examination_report"][
        "exam_findings"
    ]

    with pytest.raises(SerenitaError) as exc_info:
        service.update_report_fields(
            service.scope.member_id,
            report_id,
            updates=[
                {"field": "exam_findings", "value": "不应保留的更新"},
                {
                    "field": "lab_result",
                    "value": "10 U/L",
                    "item_id": "not-a-lab-item",
                },
            ],
        )

    assert error_http_status(exc_info.value) == 400
    assert (
        service.get_report(service.scope.member_id, report_id)["examination_report"]["exam_findings"]
        == original_findings
    )


def test_add_lab_report_item_restores_dictionary_item_and_invalidates_analysis(service):
    payload = report_payload()
    payload["lab_test_results"].append(
        {
            "item_id": "item-ast",
            "item_name_zh": "天门冬氨酸氨基转移酶",
            "aliases": ["谷草转氨酶"],
            "category_name": "肝功能",
            "result_text": "32 U/L",
            "reference_text": "15-40 U/L",
            "flag_text": "正常",
        }
    )
    created = create(service, report=payload)
    report_id = created["report_id"]
    service.delete_lab_report_items(service.scope.member_id, report_id, item_ids=["item-ast"])
    service.write_report_analysis(
        service.scope.member_id,
        report_id=report_id,
        analysis_content="当前医疗报告解读。",
    )

    updated = service.add_lab_report_item(
        service.scope.member_id,
        report_id,
        item_id="item-ast",
        result_text="35 U/L",
        reference_text="15-40 U/L",
        flag_text="正常",
    )

    assert [item["item_id"] for item in updated["lab_test_results"]] == [
        "item-alt",
        "item-ast",
    ]
    restored = next(
        item for item in updated["lab_test_results"] if item["item_id"] == "item-ast"
    )
    assert restored["item_name_zh"] == "天门冬氨酸氨基转移酶"
    assert restored["result_text"] == "35 U/L"
    assert updated["analysis_outdated"] is True

    with pytest.raises(SerenitaError) as exc_info:
        service.add_lab_report_item(
            service.scope.member_id,
            report_id,
            item_id="item-ast",
            result_text="36 U/L",
            reference_text=None,
            flag_text="偏高",
        )
    assert error_http_status(exc_info.value) == 400
    assert exc_info.value.detail["code"] == "INVALID_REPORT_LAB_ITEM_ADD"
    assert "已存在" in exc_info.value.detail["message"]


def test_add_lab_report_items_adds_multiple_results_in_one_transaction(service):
    payload = report_payload()
    payload["lab_test_results"].extend(
        [
            {
                "item_id": "item-ast",
                "item_name_zh": "天门冬氨酸氨基转移酶",
                "aliases": ["谷草转氨酶"],
                "category_name": "肝功能",
                "result_text": "32 U/L",
                "reference_text": "15-40 U/L",
                "flag_text": "正常",
            },
            {
                "item_id": "item-albumin",
                "item_name_zh": "白蛋白",
                "aliases": [],
                "category_name": "肝功能",
                "result_text": "45 g/L",
                "reference_text": "40-55 g/L",
                "flag_text": "正常",
            },
        ]
    )
    created = create(service, report=payload)
    report_id = created["report_id"]
    service.delete_lab_report_items(
        service.scope.member_id, report_id, item_ids=["item-ast", "item-albumin"]
    )
    service.write_report_analysis(
        service.scope.member_id,
        report_id=report_id,
        analysis_content="当前医疗报告解读。",
    )

    updated = service.add_lab_report_items(
        service.scope.member_id,
        report_id,
        items=[
            {
                "item_id": "item-ast",
                "result_text": "35 U/L",
                "reference_text": "15-40 U/L",
                "flag_text": "正常",
            },
            {
                "item_id": "item-albumin",
                "result_text": "44 g/L",
            },
        ],
    )

    assert [item["item_id"] for item in updated["lab_test_results"]] == [
        "item-alt",
        "item-ast",
        "item-albumin",
    ]
    albumin = next(
        item
        for item in updated["lab_test_results"]
        if item["item_id"] == "item-albumin"
    )
    assert albumin["reference_text"] is None
    assert albumin["flag_text"] == "未标记"
    assert updated["analysis_outdated"] is True


def test_add_lab_report_items_rolls_back_all_results_when_one_is_invalid(service):
    payload = report_payload()
    payload["lab_test_results"].append(
        {
            "item_id": "item-ast",
            "item_name_zh": "天门冬氨酸氨基转移酶",
            "aliases": ["谷草转氨酶"],
            "category_name": "肝功能",
            "result_text": "32 U/L",
            "reference_text": "15-40 U/L",
            "flag_text": "正常",
        }
    )
    created = create(service, report=payload)
    report_id = created["report_id"]
    service.delete_lab_report_items(service.scope.member_id, report_id, item_ids=["item-ast"])

    with pytest.raises(SerenitaError) as exc_info:
        service.add_lab_report_items(
            service.scope.member_id,
            report_id,
            items=[
                {"item_id": "item-ast", "result_text": "35 U/L"},
                {"item_id": "missing-item", "result_text": "1"},
            ],
        )

    assert error_http_status(exc_info.value) == 404
    assert exc_info.value.detail["code"] == "REPORT_LAB_ITEMS_NOT_FOUND"
    assert [
        item["item_id"]
        for item in service.get_report(service.scope.member_id, report_id)["lab_test_results"]
    ] == ["item-alt"]


def test_delete_lab_report_items_removes_multiple_targets_and_invalidates_analysis(service):
    payload = report_payload()
    payload["lab_test_results"].extend(
        [
            {
                "item_id": "item-ast",
                "item_name_zh": "天门冬氨酸氨基转移酶",
                "aliases": ["谷草转氨酶"],
                "category_name": "肝功能",
                "result_text": "32 U/L",
                "reference_text": "15-40 U/L",
                "flag_text": "正常",
            },
            {
                "item_id": "item-albumin",
                "item_name_zh": "白蛋白",
                "aliases": [],
                "category_name": "肝功能",
                "result_text": "45 g/L",
                "reference_text": "40-55 g/L",
                "flag_text": "正常",
            },
        ]
    )
    created = create(service, report=payload)
    report_id = created["report_id"]
    service.write_report_analysis(
        service.scope.member_id,
        report_id=report_id,
        analysis_content="当前医疗报告解读。",
    )

    updated = service.delete_lab_report_items(
        service.scope.member_id,
        report_id,
        item_ids=["item-alt", "item-ast"],
    )

    assert [item["item_id"] for item in updated["lab_test_results"]] == [
        "item-albumin"
    ]
    assert updated["analysis_outdated"] is True
    assert {
        item["item_id"] for item in service.read_lab_dictionary(service.scope.member_id)["items"]
    } >= {"item-alt", "item-ast", "item-albumin"}


def test_delete_lab_report_items_rejects_deleting_all_indicators(service):
    created = create(service)
    report_id = created["report_id"]

    with pytest.raises(SerenitaError) as exc_info:
        service.delete_lab_report_items(
            service.scope.member_id,
            report_id,
            item_ids=["item-alt"],
        )

    assert error_http_status(exc_info.value) == 400
    assert exc_info.value.detail["code"] == "INVALID_REPORT_LAB_ITEMS_DELETE"
    assert "最后一个指标" in exc_info.value.detail["message"]
    assert [
        item["item_id"]
        for item in service.get_report(service.scope.member_id, report_id)["lab_test_results"]
    ] == ["item-alt"]


def test_catalog_and_evidence_read_current_state(service):
    created = create(service, text="首份", message_id="base")
    assert created["report_id"]
    resource = service.validate_report_context(service.scope.member_id, created["report_id"])
    assert list(resource) == [
        "resource_type",
        "resource_id",
        "member_id",
        "report_time",
        "report_type",
        "report_name",
        "captured_created_at",
        "captured_updated_at",
    ]
    assert resource["resource_id"] == created["report_id"]
    detail = service.get_report(service.scope.member_id, created["report_id"])
    assert resource["report_name"] == detail["report_name"]
    state = service.report_resource_state(service.scope.member_id, created["report_id"])
    assert state == {
        "resource_type": "report",
        "resource_id": created["report_id"],
        "member_id": service.scope.member_id,
        "availability": "available",
        "current_created_at": resource["captured_created_at"],
        "current_updated_at": resource["captured_updated_at"],
    }
    catalog = service.read_report_catalog(service.scope.member_id)
    assert created["report_id"] in catalog["report_ids"]
    page = service.query_evidence(
        service.scope.member_id,
        report_ids=catalog["report_ids"],
    )
    assert "next_cursor" not in page
    assert page["total"] == 1


def test_report_resource_state_becomes_deleted_after_deletion(service):
    created = create(service)
    report_id = created["report_id"]
    service.delete_report(service.scope.member_id, report_id)

    assert service.report_resource_state(service.scope.member_id, report_id) == {
        "resource_type": "report",
        "resource_id": report_id,
        "member_id": service.scope.member_id,
        "availability": "deleted",
    }


def test_read_report_catalog_supports_inclusive_date_bounds(service):
    early_report = report_payload()
    early_report["report_time"] = "2026-08-05T08:00:00+08:00"
    create(service, text="较早医疗报告", report=early_report)

    middle_report = report_payload()
    middle_report["report_time"] = "2026-08-08T08:00:00+08:00"
    middle = create(service, text="中间医疗报告", report=middle_report)

    late_report = report_payload()
    late_report["report_time"] = "2026-08-10T08:00:00+08:00"
    create(service, text="较晚医疗报告", report=late_report)

    bounded = service.read_report_catalog(
        service.scope.member_id,
        after_date="2026-08-06",
        before_date="2026-08-09",
    )
    assert bounded["report_ids"] == [middle["report_id"]]

    inclusive = service.read_report_catalog(
        service.scope.member_id,
        after_date="2026-08-08",
        before_date="2026-08-08",
    )
    assert inclusive["report_ids"] == [middle["report_id"]]


def test_read_lab_dictionary_returns_complete_snapshot(service):
    payload = report_payload()
    payload["lab_test_results"].append(
        {
            "item_id": "item-ast",
            "item_name_zh": "天门冬氨酸氨基转移酶",
            "aliases": ["谷草转氨酶"],
            "category_name": "肝功能",
            "result_text": "28 U/L",
            "reference_text": "13-35 U/L",
            "flag_text": "正常",
        }
    )
    create(service, text="首份", message_id="base", report=payload)
    result = service.read_lab_dictionary(service.scope.member_id)
    assert result["total"] == len(result["items"])
    assert result["total"] >= 2
    assert "categories" in result
    assert "next_cursor" not in result


def test_query_evidence_returns_complete_snapshot(service):
    first = create(service, text="首份", message_id="base")
    second = create(service, text="第二份", message_id="second")
    report_ids = [first["report_id"], second["report_id"]]

    result = service.query_evidence(
        service.scope.member_id,
        report_ids=report_ids,
    )
    assert result["total"] == 2
    assert len(result["reports"]) == 2
    assert "next_cursor" not in result
    assert {report["report_id"] for report in result["reports"]} == set(report_ids)


def test_read_report_analysis_returns_complete_derived_entries(service):
    created = create(service, text="首份", message_id="base")
    report_id = created["report_id"]
    service.write_report_analysis(
        service.scope.member_id,
        report_id=report_id,
        analysis_content="自由格式解读：按需复查。",
    )

    result = service.read_report_analysis(
        service.scope.member_id,
        report_ids=[report_id],
    )
    assert result["total"] == 1
    assert "next_cursor" not in result
    assert len(result["analyses"]) == 1
    assert result["analyses"][0]["report_id"] == report_id
    assert result["analyses"][0]["analysis_content"].endswith("按需复查。")


def test_analysis_text_normalization_does_not_enforce_writing_format(service):
    plain_text = "这是不含 Markdown 板块标题的解读。"
    bullet_text = "- 近期关注重点——按需复查。"
    fenced_text = "```markdown\n## 好消息\n\n无明显异常。\n```"

    assert normalize_analysis_content(f"  {plain_text}\n") == plain_text
    assert normalize_analysis_content(bullet_text) == bullet_text
    assert normalize_analysis_content(fenced_text) == fenced_text
    with pytest.raises(ValueError, match="不能为空"):
        normalize_analysis_content("   ")

    assert semantic_lab_category("凝血功能", ()) == "凝血功能"
    with pytest.raises(ValueError, match="必须由模型判断"):
        semantic_lab_category("1", ())


def test_query_evidence_fields_projection_defaults_and_sources(service):
    created = create(service, text="首份", message_id="base")
    report_id = created["report_id"]

    default_page = service.query_evidence(service.scope.member_id, report_ids=[report_id])
    assert default_page["total"] == 1
    default_report = default_page["reports"][0]
    assert set(default_report) == {
        "report_id",
        "report_type",
        "report_name",
        "report_time",
        "institution_name",
        "lab_test_results",
        "examination_report",
        "pathology_report",
        "surgery_report",
        "outpatient_report",
        "emergency_report",
        "other_report",
    }
    assert "sources" not in default_report
    assert "analysis_outdated" not in default_report

    with pytest.raises(ValueError, match="fields"):
        service.query_evidence(
            service.scope.member_id,
            report_ids=[report_id],
            fields=["analysis_outdated"],
        )

    source_page = service.query_evidence(
        service.scope.member_id,
        report_ids=[report_id],
        fields=["sources"],
    )
    source_report = source_page["reports"][0]
    assert set(source_report) == {
        "report_id",
        "report_type",
        "report_name",
        "report_time",
        "sources",
    }
    assert source_report["sources"]

    mixed_page = service.query_evidence(
        service.scope.member_id,
        report_ids=[report_id],
        fields=["lab_test_results", "sources"],
    )
    mixed_report = mixed_page["reports"][0]
    assert set(mixed_report) == {
        "report_id",
        "report_type",
        "report_name",
        "report_time",
        "lab_test_results",
        "sources",
    }

    with pytest.raises(ValueError, match="fields"):
        service.query_evidence(
            service.scope.member_id,
            report_ids=[report_id],
            fields=["unknown_field"],
        )


def test_query_evidence_strips_redundant_nested_foreign_keys(service):
    lab = create(service, text="检验报告", message_id="lab")
    exam = create(
        service,
        text="检查报告",
        message_id="exam",
        report=report_payload(report_type="检查报告"),
    )

    evidence = service.query_evidence(
        service.scope.member_id,
        report_ids=[lab["report_id"], exam["report_id"]],
    )
    by_id = {item["report_id"]: item for item in evidence["reports"]}

    lab_item = by_id[lab["report_id"]]["lab_test_results"][0]
    assert set(lab_item) == {
        "item_id",
        "item_name_zh",
        "result_text",
        "reference_text",
        "flag_text",
    }
    assert "report_id" not in lab_item
    assert "category_name" not in lab_item

    examination = by_id[exam["report_id"]]["examination_report"]
    assert set(examination) == {
        "exam_name",
        "clinical_diagnosis",
        "exam_method",
        "exam_findings",
        "exam_diagnosis",
    }
    assert "report_id" not in examination


@pytest.mark.parametrize("tool_name", ["create_report", "link_duplicate_sources", "merge_report", "reclassify_report"])
def test_write_tools_validate_before_persistence_and_accept_corrected_content(service, tool_name):
    from types import SimpleNamespace
    from backend.app.plugins.medical_report.registry import build_tools
    from backend.app.plugins.runtime_context import PluginRuntimeContext

    created = create(service, message_id="original")
    report_id = created["report_id"]
    before = service.get_report(service.scope.member_id, report_id)
    reports_before = service.list_reports(service.scope.member_id)
    files_before = set(service.paths.report_attachments_dir(service.account_id).glob("*"))
    dictionary_before = service.repository.lab_dictionary(service.scope.member_id)
    tools = build_tools(runtime_context=PluginRuntimeContext(
        account_id=service.account_id, member_id=service.scope.member_id,
        event_recorder=lambda _event: None,
        service_factory=lambda _name: service,
    ))
    tool = next(value for value in tools if value.name == tool_name)
    ctx = SimpleNamespace(account_id=service.account_id, member_id=service.scope.member_id,
        session_id="session", turn_id="turn", input_text="添加医疗报告原文",
        memory={"current_message_id": "new-message", "visible_attachments": {}})
    payload = report_payload()
    arguments = {"report": payload, "sources": [{"source_type": "conversation_text"}]}
    observations = []
    if tool_name in {"link_duplicate_sources", "merge_report"}:
        arguments["target_report_id"] = report_id
    if tool_name == "merge_report":
        payload["lab_test_results"].append({**payload["lab_test_results"][0], "item_id": "item-ast", "item_name_zh": "天冬氨酸氨基转移酶", "aliases": []})
    if tool_name == "reclassify_report":
        arguments["report_id"] = report_id
        source = before["sources"][0]
        arguments["sources"] = [{"source_type": "report_source", "read_call_id": "read-one", "report_id": report_id, "resource_id": source["resource_id"]}]
        observations = [{"name": "read_report_information", "call_id": "read-one", "output": {"reports": [before]}}]
    payload["report_name"] = "与分类不一致的名称"
    with pytest.raises(ValueError, match="完全一致"):
        tool.run(tool.bind_runtime_arguments(arguments, context=ctx, observations=observations))
    assert service.get_report(service.scope.member_id, report_id) == before
    assert service.list_reports(service.scope.member_id) == reports_before
    assert service.repository.lab_dictionary(service.scope.member_id) == dictionary_before
    assert set(service.paths.report_attachments_dir(service.account_id).glob("*")) == files_before
    payload["report_name"] = "肝功能"
    if tool_name == "reclassify_report":
        arguments["report"] = report_payload(report_type="检查报告")
    result = tool.run(tool.bind_runtime_arguments(arguments, context=ctx, observations=observations))
    assert result.output["report_id"]
    assert "resolved_context_items" not in result.effects
    if tool_name == "reclassify_report":
        assert result.output["report_type"] == "检查报告"
        assert result.output["report_time"] == before["report_time"]
        assert result.output["sources"] == before["sources"]
    elif tool_name == "merge_report":
        assert result.output["added_item_ids"] == ["item-ast"]
    elif tool_name == "link_duplicate_sources":
        after = service.get_report(service.scope.member_id, report_id)
        assert len(after["sources"]) == 2
        assert after["lab_test_results"] == before["lab_test_results"]
    else:
        assert service.list_reports(service.scope.member_id)["total"] == reports_before["total"] + 1


@pytest.mark.parametrize("failure", ["unread", "changed", "missing"])
def test_write_rechecks_saved_source_authorization_and_integrity(service, failure):
    created = create(service)
    report_id = created["report_id"]
    before = service.get_report(service.scope.member_id, report_id)
    source = before["sources"][0]
    arguments = write_arguments(report=report_payload(report_type="检查报告"))
    arguments["sources"] = [{"source_type": "report_source", "read_call_id": "read-one", "report_id": report_id, "resource_id": source["resource_id"]}]
    if failure != "unread":
        arguments["authorized_report_sources"] = {f"read-one\0{report_id}\0{source['resource_id']}": source}
        path, _, _ = service.source_download(service.scope.member_id, report_id, source["resource_id"])
        if failure == "changed":
            path.write_text("已被更新")
        else:
            path.unlink()
    with pytest.raises((PermissionError, ValueError, FileNotFoundError)):
        service.reclassify_report(service.scope.member_id, report_id, **arguments)
    assert service.get_report(service.scope.member_id, report_id) == before
