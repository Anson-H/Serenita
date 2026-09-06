from member_support import account_id as account_id_for, member_id
import os
import tempfile
from tests.api_client import TestClient


def test_report_page_field_crud_uses_last_valid_write_and_creates_no_conversation():
    previous = os.environ.get("DATA_ROOT")
    directory = tempfile.TemporaryDirectory()
    os.environ["DATA_ROOT"] = directory.name
    try:
        from backend.app.main import create_app
        from backend.app.repositories.report_repository import ReportRepository
        from backend.app.storage.paths import app_paths

        client = TestClient(create_app())
        assert client.post(
            "/api/auth/sign_up",
            json={
                "account": "alice",
                "account_name": "Alice",
                "password": "secret",
                "confirm_password": "secret",
            },
        ).status_code == 200
        repository = ReportRepository(account_id_for("alice"), app_paths())
        source_path = app_paths().report_attachment_path(
            account_id_for("alice"), "FILE-field-crud", "txt"
        )
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text("原始正文", encoding="utf-8")
        repository.register_source_file(
            member_id("alice"),
            resource_id="FILE-field-crud",
            relative_path=str(
                source_path.relative_to(app_paths().account_root(account_id_for("alice")))
            ),
            mime_type="text/plain",
            size_bytes=source_path.stat().st_size,
            sha256="sha-field-crud",
            source_kind="unknown",
        )
        report_id = repository.create_report(
            member_id("alice"),
            {
                "report_type": "其它报告",
                "report_name": "原始名称",
                "report_time": "2026-08-16T09:00:00+08:00",
                "other_report": {"report_body": "原始正文"},
            },
            resource_id="FILE-field-crud",
        )
        renamed = client.patch(
            f"/api/members/{member_id('alice')}/reports/{report_id}/fields",
            json={
                "field": "report_name",
                "value": "更新名称",
            },
        )
        assert renamed.status_code == 200
        assert renamed.json()["report_name"] == "更新名称"

        analyzed = client.patch(
            f"/api/members/{member_id('alice')}/reports/{report_id}/fields",
            json={
                "field": "analysis_content",
                "value": "手工解读",
            },
        )
        assert analyzed.status_code == 200
        assert analyzed.json()["analysis_content"] == "手工解读"

        cleared_analysis = client.patch(
            f"/api/members/{member_id('alice')}/reports/{report_id}/fields",
            json={
                "field": "analysis_content",
                "value": None,
            },
        )
        assert cleared_analysis.status_code == 200
        assert cleared_analysis.json()["analysis_content"] == ""
        assert cleared_analysis.json()["has_analysis"] is False

        retimed = client.patch(
            f"/api/members/{member_id('alice')}/reports/{report_id}/fields",
            json={
                "field": "report_time",
                "value": "2026-08-17 10:30",
            },
        )
        assert retimed.status_code == 200
        assert retimed.json()["report_time"].startswith("2026-08-17T10:30")

        later = client.patch(
            f"/api/members/{member_id('alice')}/reports/{report_id}/fields",
            json={
                "field": "report_body",
                "value": "最后写入生效",
            },
        )
        assert later.status_code == 200
        assert later.json()["other_report"]["report_body"] == "最后写入生效"

        empty_required = client.patch(
            f"/api/members/{member_id('alice')}/reports/{report_id}/fields",
            json={
                "field": "report_body",
                "value": "",
            },
        )
        assert empty_required.status_code == 400
        assert client.get("/api/conversations").json()["sessions"] == []
    finally:
        directory.cleanup()
        if previous is None:
            os.environ.pop("DATA_ROOT", None)
        else:
            os.environ["DATA_ROOT"] = previous


def test_report_http_surface_exposes_only_explicit_page_crud_mutations():
    previous = os.environ.get("DATA_ROOT")
    directory = tempfile.TemporaryDirectory()
    os.environ["DATA_ROOT"] = directory.name
    try:
        from backend.app.main import create_app

        client = TestClient(create_app())
        signup = client.post(
            "/api/auth/sign_up",
            json={
                "account": "alice",
                "account_name": "Alice",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        assert signup.status_code == 200
        assert "session_token" not in signup.json()
        assert client.get(f"/api/members/{member_id('alice')}/reports").status_code == 200

        routes = {
            (method, route.path)
            for route in client.app.routes
            for method in getattr(route, "methods", set())
        }
        assert ("GET", "/api/members/{member_id}/reports") in routes
        assert ("POST", "/api/members/{member_id}/reports") in routes
        assert ("GET", "/api/members/{member_id}/reports/{report_id}") in routes
        assert (
            "POST",
            "/api/members/{member_id}/reports/{report_id}/source-files",
        ) in routes
        assert ("PATCH", "/api/members/{member_id}/reports/{report_id}/fields") in routes
        assert ("POST", "/api/members/{member_id}/reports/{report_id}/lab-items") in routes
        assert ("DELETE", "/api/members/{member_id}/reports/{report_id}/lab-items/{item_id}") in routes
        assert ("DELETE", "/api/members/{member_id}/reports/{report_id}") in routes
        forbidden = {
            ("POST", "/api/upload-report"),
            ("POST", "/api/report-upload-batches"),
            ("POST", "/api/members/{member_id}/reports/{report_id}/analysis"),
            ("PUT", "/api/members/{member_id}/reports/{report_id}"),
            ("PATCH", "/api/members/{member_id}/reports/{report_id}/field"),
        }
        assert routes.isdisjoint(forbidden)
        assert not any("report-analysis-jobs" in path for _, path in routes)
    finally:
        directory.cleanup()
        if previous is None:
            os.environ.pop("DATA_ROOT", None)
        else:
            os.environ["DATA_ROOT"] = previous


def test_report_page_can_add_and_delete_lab_items_without_a_conversation():
    previous = os.environ.get("DATA_ROOT")
    directory = tempfile.TemporaryDirectory()
    os.environ["DATA_ROOT"] = directory.name
    try:
        from backend.app.main import create_app

        client = TestClient(create_app())
        assert client.post(
            "/api/auth/sign_up",
            json={
                "account": "alice",
                "account_name": "Alice",
                "password": "secret",
                "confirm_password": "secret",
            },
        ).status_code == 200
        created = client.post(
            f"/api/members/{member_id('alice')}/reports",
            json={
                "report_type": "检验报告",
                "report_name": "肝功能",
                "report_time": "2026-08-21T09:30:00+08:00",
                "lab_test_results": [
                    {
                        "item_id": "item-alt",
                        "item_name_zh": "丙氨酸氨基转移酶",
                        "aliases": ["谷丙转氨酶"],
                        "category_name": "肝功能",
                        "result_text": "65 U/L",
                        "reference_text": "9-50 U/L",
                        "flag_text": "偏高",
                    },
                    {
                        "item_id": "item-ast",
                        "item_name_zh": "天门冬氨酸氨基转移酶",
                        "aliases": ["谷草转氨酶"],
                        "category_name": "肝功能",
                        "result_text": "32 U/L",
                        "reference_text": "15-40 U/L",
                        "flag_text": "正常",
                    },
                ],
            },
        )
        assert created.status_code == 201, created.text
        report_id = created.json()["report_id"]

        deleted = client.delete(
            f"/api/members/{member_id('alice')}/reports/{report_id}/lab-items/item-ast"
        )
        assert deleted.status_code == 200, deleted.text
        assert [
            item["item_id"] for item in deleted.json()["lab_test_results"]
        ] == ["item-alt"]

        last_item = client.delete(
            f"/api/members/{member_id('alice')}/reports/{report_id}/lab-items/item-alt"
        )
        assert last_item.status_code == 400
        assert last_item.json()["detail"]["code"] == "INVALID_REPORT_LAB_ITEMS_DELETE"

        added = client.post(
            f"/api/members/{member_id('alice')}/reports/{report_id}/lab-items",
            json={
                "item_id": "item-ast",
                "result_text": "35 U/L",
                "reference_text": "15-40 U/L",
                "flag_text": "正常",
            },
        )
        assert added.status_code == 201, added.text
        assert {
            item["item_id"] for item in added.json()["lab_test_results"]
        } == {"item-alt", "item-ast"}

        duplicate = client.post(
            f"/api/members/{member_id('alice')}/reports/{report_id}/lab-items",
            json={
                "item_id": "item-ast",
                "result_text": "36 U/L",
                "reference_text": None,
                "flag_text": "偏高",
            },
        )
        assert duplicate.status_code == 400
        assert "已存在" in duplicate.json()["detail"]["message"]
        assert client.get("/api/conversations").json()["sessions"] == []
    finally:
        directory.cleanup()
        if previous is None:
            os.environ.pop("DATA_ROOT", None)
        else:
            os.environ["DATA_ROOT"] = previous


def test_manual_report_creation_is_page_crud_without_conversation_or_fake_source():
    previous = os.environ.get("DATA_ROOT")
    directory = tempfile.TemporaryDirectory()
    os.environ["DATA_ROOT"] = directory.name
    try:
        from backend.app.main import create_app

        client = TestClient(create_app())
        assert client.post(
            "/api/auth/sign_up",
            json={
                "account": "alice",
                "account_name": "Alice",
                "password": "secret",
                "confirm_password": "secret",
            },
        ).status_code == 200

        created = client.post(
            f"/api/members/{member_id('alice')}/reports",
            json={
                "report_type": "检查报告",
                "report_name": "腹部超声",
                "report_time": "2026-08-21T09:30:00+08:00",
                "institution_name": "测试医院",
                "examination_report": {
                    "exam_name": "腹部超声",
                    "clinical_diagnosis": None,
                    "exam_method": "超声",
                    "exam_findings": "未见明显异常",
                    "exam_diagnosis": "建议结合临床",
                },
            },
        )

        assert created.status_code == 201, created.text
        detail = created.json()
        assert detail["report_type"] == "检查报告"
        assert detail["report_name"] == "腹部超声"
        assert detail["sources"] == []
        assert detail["examination_report"]["exam_name"] == "腹部超声"
        listed = client.get(f"/api/members/{member_id('alice')}/reports").json()
        assert listed["total"] == 1
        assert listed["reports"][0]["member_id"] == member_id("alice")
        assert listed["reports"][0]["report_name"] == "腹部超声"
        assert client.get("/api/conversations").json()["sessions"] == []

        invalid = client.post(
            f"/api/members/{member_id('alice')}/reports",
            json={
                "report_type": "其它报告",
                "report_name": "空正文",
                "report_time": "2026-08-21T09:30:00+08:00",
                "other_report": {"report_body": ""},
            },
        )
        assert invalid.status_code == 422
        assert client.get("/api/conversations").json()["sessions"] == []
    finally:
        directory.cleanup()
        if previous is None:
            os.environ.pop("DATA_ROOT", None)
        else:
            os.environ["DATA_ROOT"] = previous


def test_report_page_can_supplement_originals_without_a_conversation():
    previous = os.environ.get("DATA_ROOT")
    directory = tempfile.TemporaryDirectory()
    os.environ["DATA_ROOT"] = directory.name
    try:
        from backend.app.main import create_app
        from backend.app.storage.paths import app_paths

        client = TestClient(create_app())
        assert client.post(
            "/api/auth/sign_up",
            json={
                "account": "alice",
                "account_name": "Alice",
                "password": "secret",
                "confirm_password": "secret",
            },
        ).status_code == 200

        created = client.post(
            f"/api/members/{member_id('alice')}/reports",
            json={
                "report_type": "其它报告",
                "report_name": "手工录入记录",
                "report_time": "2026-08-21T09:30:00+08:00",
                "other_report": {"report_body": "已经整理好的报告事实"},
            },
        )
        assert created.status_code == 201, created.text
        report_id = created.json()["report_id"]
        endpoint = (
            f"/api/members/{member_id('alice')}/reports/{report_id}/source-files"
        )

        first_content = b"\xff\xd8\xfffirst-original"
        first = client.post(
            endpoint,
            files=[("files", ("first.jpg", first_content, "image/jpeg"))],
        )
        assert first.status_code == 201, first.text
        first_sources = first.json()["sources"]
        assert len(first_sources) == 1
        assert "original_filename" not in first_sources[0]
        assert first_sources[0]["resource_id"].startswith("RESOURCE-")
        assert first_sources[0]["filename"] == f"{first_sources[0]['resource_id']}.jpg"
        assert first_sources[0]["size_bytes"] == len(first_content)
        assert first_sources[0]["created_at"]
        assert "uploaded_at" not in first_sources[0]
        assert "uploaded_at" not in first.json()
        assert first_sources[0]["is_primary"] is True
        assert first_sources[0]["thumbnail_url"].endswith("/thumbnail")
        stored_original = (
            app_paths().account_root(account_id_for("alice"))
            / "reports"
            / "attachments"
            / first_sources[0]["filename"]
        )
        assert stored_original.read_bytes() == first_content
        downloaded = client.get(first_sources[0]["download_url"])
        assert downloaded.status_code == 200
        assert downloaded.content == first_content
        assert first_sources[0]["filename"] in downloaded.headers["content-disposition"]

        second_content = b"\x89PNG\r\n\x1a\nsecond-original"
        second = client.post(
            endpoint,
            files=[("files", ("second.png", second_content, "image/png"))],
        )
        assert second.status_code == 201, second.text
        second_sources = second.json()["sources"]
        assert [source["filename"] for source in second_sources] == [
            f"{second_sources[0]['resource_id']}.jpg",
            f"{second_sources[1]['resource_id']}.png",
        ]
        assert [source["is_primary"] for source in second_sources] == [True, False]

        duplicate = client.post(
            endpoint,
            files=[("files", ("first-copy.jpg", first_content, "image/jpeg"))],
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["code"] == "REPORT_SOURCE_DUPLICATE"
        assert len(client.get(endpoint.rsplit("/source-files", 1)[0]).json()["sources"]) == 2
        assert client.get("/api/conversations").json()["sessions"] == []
    finally:
        directory.cleanup()
        if previous is None:
            os.environ.pop("DATA_ROOT", None)
        else:
            os.environ["DATA_ROOT"] = previous


def test_report_page_delete_does_not_create_a_conversation():
    previous = os.environ.get("DATA_ROOT")
    directory = tempfile.TemporaryDirectory()
    os.environ["DATA_ROOT"] = directory.name
    try:
        from backend.app.main import create_app
        from backend.app.repositories.report_repository import ReportRepository
        from backend.app.storage.paths import app_paths

        client = TestClient(create_app())
        assert client.post(
            "/api/auth/sign_up",
            json={
                "account": "alice",
                "account_name": "Alice",
                "password": "secret",
                "confirm_password": "secret",
            },
        ).status_code == 200

        paths = app_paths()
        repository = ReportRepository(account_id_for("alice"), paths)
        source_path = paths.report_attachment_path(
            account_id_for("alice"), "FILE-ui-delete", "jpg"
        )
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(b"\xff\xd8\xffreport")
        repository.register_source_file(
            member_id("alice"),
            resource_id="FILE-ui-delete",
            relative_path=str(source_path.relative_to(paths.account_root(account_id_for("alice")))),
            mime_type="image/jpeg",
            size_bytes=source_path.stat().st_size,
            sha256="sha-ui-delete",
            source_kind="photo",
        )
        report_id = repository.create_report(
            member_id("alice"),
            {
                "report_type": "其它报告",
                "report_name": "待删除报告",
                "report_time": "2026-08-16T09:00:00+08:00",
                "other_report": {"report_body": "测试内容"},
            },
            resource_id="FILE-ui-delete",
        )
        detail = client.get(f"/api/members/{member_id('alice')}/reports/{report_id}")
        assert detail.status_code == 200
        assert client.get("/api/conversations").json()["sessions"] == []

        deleted = client.delete(f"/api/members/{member_id('alice')}/reports/{report_id}")

        assert deleted.status_code == 200
        assert deleted.json() == {"report_id": report_id, "deleted": True}
        assert client.get(f"/api/members/{member_id('alice')}/reports/{report_id}").status_code == 404
        after_delete = client.patch(
            f"/api/members/{member_id('alice')}/reports/{report_id}/fields",
            json={"field": "report_name", "value": "无法恢复"},
        )
        assert after_delete.status_code == 404
        assert "已不存在" in after_delete.json()["detail"]["message"]
        assert client.get("/api/conversations").json()["sessions"] == []
    finally:
        directory.cleanup()
        if previous is None:
            os.environ.pop("DATA_ROOT", None)
        else:
            os.environ["DATA_ROOT"] = previous
