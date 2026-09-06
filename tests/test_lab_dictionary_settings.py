from __future__ import annotations
from member_support import account_id as account_id_for, member_id
from tests.api_client import TestClient


def _signup(client: TestClient, account: str) -> None:
    response = client.post(
        "/api/auth/sign_up",
        json={
            "account": account,
            "account_name": account.title(),
            "password": "secret",
            "confirm_password": "secret",
        },
    )
    assert response.status_code == 200, response.text


def _create_category(client: TestClient, revision: str, name: str) -> dict:
    response = client.post(
        "/api/account-settings/lab-dictionary/categories",
        json={
            "category_name": name,
            "description": None,
            "expected_dictionary_revision": revision,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["dictionary"]


def _create_item(
    client: TestClient, revision: str, name: str, categories: list[str]
) -> dict:
    response = client.post(
        "/api/account-settings/lab-dictionary/items",
        json={
            "item_name_zh": name,
            "aliases": [f"{name}-别名"],
            "description": None,
            "primary_category_name": categories[0],
            "related_category_names": categories[1:],
            "expected_dictionary_revision": revision,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["dictionary"]


def test_account_dictionary_isolated_crud_and_revision(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    from backend.app.main import create_app

    app = create_app()
    alice = TestClient(app)
    bob = TestClient(app)
    _signup(alice, "alice")
    _signup(bob, "bob")

    alice_dictionary = alice.get("/api/account-settings/lab-dictionary").json()
    alice_dictionary = _create_category(
        alice, alice_dictionary["dictionary_revision"], "肝功能"
    )
    alice_dictionary = _create_item(
        alice,
        alice_dictionary["dictionary_revision"],
        "谷丙转氨酶",
        ["肝功能"],
    )
    assert alice_dictionary["summary"] == {
        "item_count": 1,
        "category_count": 1,
        "relation_count": 1,
    }
    assert bob.get("/api/account-settings/lab-dictionary").json()["summary"][
        "item_count"
    ] == 0

    stale = alice.post(
        "/api/account-settings/lab-dictionary/categories",
        json={
            "category_name": "肾功能",
            "description": None,
            "expected_dictionary_revision": "stale",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "LAB_DICTIONARY_REVISION_CONFLICT"

    conflict = alice.post(
        "/api/account-settings/lab-dictionary/items",
        json={
            "item_name_zh": "新指标",
            "aliases": ["谷丙转氨酶"],
            "description": None,
            "primary_category_name": "肝功能",
            "related_category_names": [],
            "expected_dictionary_revision": alice_dictionary[
                "dictionary_revision"
            ],
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "LAB_DICTIONARY_NAME_CONFLICT"
    assert conflict.json()["detail"]["conflicting_item_name_zh"] == "谷丙转氨酶"


def test_same_display_name_is_allowed_in_different_primary_categories(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    from backend.app.main import create_app

    client = TestClient(create_app())
    _signup(client, "alice")
    dictionary = client.get("/api/account-settings/lab-dictionary").json()
    for category in ("血常规", "尿常规", "便常规"):
        dictionary = _create_category(
            client, dictionary["dictionary_revision"], category
        )
        dictionary = _create_item(
            client, dictionary["dictionary_revision"], "红细胞", [category]
        )

    red_cells = [
        item for item in dictionary["items"] if item["item_name_zh"] == "红细胞"
    ]
    assert len(red_cells) == 3
    assert len({item["item_id"] for item in red_cells}) == 3
    assert {item["primary_category_name"] for item in red_cells} == {
        "血常规", "尿常规", "便常规"
    }


def test_existing_item_name_conflict_can_merge_without_overwriting_reports(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    from backend.app.main import create_app
    from backend.app.repositories.report_repository import ReportRepository
    from backend.app.storage.paths import app_paths

    client = TestClient(create_app())
    _signup(client, "alice")
    repository = ReportRepository(account_id_for("alice"), app_paths())
    source_path = app_paths().report_attachment_path(
        account_id_for("alice"), "FILE-merge", "txt"
    )
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("检验原件", encoding="utf-8")
    repository.register_source_file(
        member_id("alice"),
        resource_id="FILE-merge",
        relative_path=str(source_path.relative_to(app_paths().account_root(account_id_for("alice")))),
        mime_type="text/plain",
        size_bytes=source_path.stat().st_size,
        sha256="dictionary-merge-source",
        source_kind="unknown",
    )
    report_id = repository.create_report(
        member_id("alice"),
        {
            "report_type": "检验报告",
            "report_name": "肝功能",
            "report_time": "2026-08-17T09:00:00+08:00",
            "lab_test_results": [
                {
                    "item_id": "item-alt-source",
                    "item_name_zh": "谷丙转氨酶",
                    "aliases": ["ALT"],
                    "category_name": "肝功能",
                    "result_text": "65 U/L",
                    "reference_text": "9–50 U/L",
                    "flag_text": "偏高",
                }
            ],
        },
        resource_id="FILE-merge",
    )
    dictionary = client.get("/api/account-settings/lab-dictionary").json()
    dictionary = _create_category(
        client, dictionary["dictionary_revision"], "综合生化"
    )
    dictionary = _create_item(
        client,
        dictionary["dictionary_revision"],
        "丙氨酸氨基转移酶",
        ["综合生化"],
    )
    target_item = next(
        row for row in dictionary["items"]
        if row["item_name_zh"] == "丙氨酸氨基转移酶"
    )

    conflict = client.patch(
        "/api/account-settings/lab-dictionary/items/item-alt-source",
        json={
            "item_name_zh": "丙氨酸氨基转移酶",
            "aliases": ["ALT", "谷丙转氨酶"],
            "description": None,
            "primary_category_name": "综合生化",
            "related_category_names": [],
            "expected_dictionary_revision": dictionary["dictionary_revision"],
        },
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"] == {
        "code": "LAB_DICTIONARY_NAME_CONFLICT",
        "message": "指标名称或别名与“丙氨酸氨基转移酶”在主分类“综合生化”中重复。",
        "conflicting_item_id": target_item["item_id"],
        "conflicting_item_name_zh": "丙氨酸氨基转移酶",
    }

    merged = client.post(
        "/api/account-settings/lab-dictionary/items/item-alt-source/merge",
        json={
            "target_item_id": target_item["item_id"],
            "expected_dictionary_revision": dictionary["dictionary_revision"],
        },
    )
    assert merged.status_code == 200, merged.text
    payload = merged.json()
    assert payload["effects"]["merged_source_item_id"] == "item-alt-source"
    assert payload["effects"]["merged_target_item_id"] == target_item["item_id"]
    assert payload["effects"]["moved_result_count"] == 1
    assert payload["effects"]["deduplicated_result_count"] == 0
    assert payload["dictionary"]["summary"]["item_count"] == 1
    item = payload["dictionary"]["items"][0]
    assert item["item_name_zh"] == "丙氨酸氨基转移酶"
    assert {"谷丙转氨酶", "ALT"}.issubset(set(item["aliases"]))
    assert item["primary_category_name"] == "综合生化"
    assert item["related_category_names"] == ["肝功能"]
    report = client.get(f"/api/members/{member_id('alice')}/reports/{report_id}").json()
    assert report["report_name"] == "综合生化"
    assert report["lab_test_results"][0]["item_name_zh"] == "丙氨酸氨基转移酶"
    assert report["lab_test_results"][0]["result_text"] == "65 U/L"
    assert source_path.exists()


def test_item_merge_rejects_different_results_in_the_same_report(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    from backend.app.main import create_app
    from backend.app.repositories.report_repository import ReportRepository
    from backend.app.storage.paths import app_paths

    client = TestClient(create_app())
    _signup(client, "alice")
    repository = ReportRepository(account_id_for("alice"), app_paths())
    source_path = app_paths().report_attachment_path(
        account_id_for("alice"), "FILE-merge-conflict", "txt"
    )
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("同一报告中的两个结果", encoding="utf-8")
    repository.register_source_file(
        member_id("alice"),
        resource_id="FILE-merge-conflict",
        relative_path=str(source_path.relative_to(app_paths().account_root(account_id_for("alice")))),
        mime_type="text/plain",
        size_bytes=source_path.stat().st_size,
        sha256="dictionary-merge-conflict",
        source_kind="unknown",
    )
    report_id = repository.create_report(
        member_id("alice"),
        {
            "report_type": "检验报告",
            "report_name": "血常规",
            "report_time": "2026-08-17T10:00:00+08:00",
            "lab_test_results": [
                {
                    "item_id": "item-a",
                    "item_name_zh": "指标甲",
                    "category_name": "血常规",
                    "result_text": "10 U/L",
                },
                {
                    "item_id": "item-b",
                    "item_name_zh": "指标乙",
                    "category_name": "血常规",
                    "result_text": "20 U/L",
                },
            ],
        },
        resource_id="FILE-merge-conflict",
    )
    dictionary = client.get("/api/account-settings/lab-dictionary").json()
    response = client.post(
        "/api/account-settings/lab-dictionary/items/item-a/merge",
        json={
            "target_item_id": "item-b",
            "expected_dictionary_revision": dictionary["dictionary_revision"],
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "LAB_DICTIONARY_MERGE_RESULT_CONFLICT"
    assert response.json()["detail"]["details"][0]["source"]["result_text"] == "10 U/L"
    after = client.get(f"/api/members/{member_id('alice')}/reports/{report_id}").json()
    assert {row["item_name_zh"] for row in after["lab_test_results"]} == {"指标甲", "指标乙"}


def test_dictionary_primary_and_related_categories_preserve_history(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    from backend.app.main import create_app
    from backend.app.repositories.report_repository import ReportRepository
    from backend.app.storage.paths import app_paths

    client = TestClient(create_app())
    _signup(client, "alice")
    repository = ReportRepository(account_id_for("alice"), app_paths())
    source_path = app_paths().report_attachment_path(
        account_id_for("alice"), "FILE-dictionary", "txt"
    )
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("检验原件", encoding="utf-8")
    repository.register_source_file(
        member_id("alice"),
        resource_id="FILE-dictionary",
        relative_path=str(source_path.relative_to(app_paths().account_root(account_id_for("alice")))),
        mime_type="text/plain",
        size_bytes=source_path.stat().st_size,
        sha256="dictionary-source",
        source_kind="unknown",
    )
    report_id = repository.create_report(
        member_id("alice"),
        {
            "report_type": "检验报告",
            "report_name": "肝功能",
            "report_time": "2026-08-17T09:00:00+08:00",
            "lab_test_results": [
                {
                    "item_id": "item-alt-rename",
                    "item_name_zh": "谷丙转氨酶",
                    "aliases": ["ALT"],
                    "category_name": "肝功能",
                    "result_text": "65 U/L",
                    "reference_text": "9–50 U/L",
                    "flag_text": "偏高",
                }
            ],
        },
        resource_id="FILE-dictionary",
    )
    dictionary = client.get("/api/account-settings/lab-dictionary").json()
    item = dictionary["items"][0]

    renamed_item = client.patch(
        f"/api/account-settings/lab-dictionary/items/{item['item_id']}",
        json={
            "item_name_zh": "丙氨酸氨基转移酶",
            "aliases": ["ALT", "谷丙转氨酶"],
            "description": "肝细胞损伤相关指标",
            "primary_category_name": "肝功能",
            "related_category_names": [],
            "expected_dictionary_revision": dictionary["dictionary_revision"],
        },
    )
    assert renamed_item.status_code == 200, renamed_item.text
    renamed_dictionary = renamed_item.json()["dictionary"]
    renamed_report = client.get(f"/api/members/{member_id('alice')}/reports/{report_id}").json()
    assert renamed_report["lab_test_results"][0]["item_name_zh"] == "丙氨酸氨基转移酶"
    renamed_item_id = renamed_dictionary["items"][0]["item_id"]

    renamed_category = client.patch(
        "/api/account-settings/lab-dictionary/categories/%E8%82%9D%E5%8A%9F%E8%83%BD",
        json={
            "category_name": "肝脏功能",
            "description": None,
            "expected_dictionary_revision": renamed_dictionary[
                "dictionary_revision"
            ],
        },
    )
    assert renamed_category.status_code == 200, renamed_category.text
    dictionary = renamed_category.json()["dictionary"]
    report = client.get(f"/api/members/{member_id('alice')}/reports/{report_id}").json()
    assert report["report_name"] == "肝脏功能"
    assert report["lab_test_results"][0]["category_name"] == "肝脏功能"

    for category_name in ("综合生化", "代谢相关"):
        dictionary = _create_category(
            client, dictionary["dictionary_revision"], category_name
        )

    changed_primary = client.patch(
        f"/api/account-settings/lab-dictionary/items/{renamed_item_id}",
        json={
            "item_name_zh": "丙氨酸氨基转移酶",
            "aliases": ["ALT", "谷丙转氨酶"],
            "description": None,
            "primary_category_name": "综合生化",
            "related_category_names": ["代谢相关"],
            "expected_dictionary_revision": dictionary["dictionary_revision"],
        },
    )
    assert changed_primary.status_code == 200, changed_primary.text
    dictionary = changed_primary.json()["dictionary"]
    item = dictionary["items"][0]
    assert item["primary_category_name"] == "综合生化"
    assert item["related_category_names"] == ["代谢相关"]
    report = client.get(f"/api/members/{member_id('alice')}/reports/{report_id}").json()
    assert report["report_name"] == "综合生化"
    assert report["lab_test_results"][0]["category_name"] == "综合生化"

    removed_related = client.patch(
        f"/api/account-settings/lab-dictionary/items/{renamed_item_id}",
        json={
            "item_name_zh": "丙氨酸氨基转移酶",
            "aliases": ["ALT", "谷丙转氨酶"],
            "description": None,
            "primary_category_name": "综合生化",
            "related_category_names": [],
            "expected_dictionary_revision": dictionary["dictionary_revision"],
        },
    )
    assert removed_related.status_code == 200, removed_related.text
    dictionary = removed_related.json()["dictionary"]
    report_after_related_change = client.get(f"/api/members/{member_id('alice')}/reports/{report_id}").json()
    assert report_after_related_change["report_name"] == "综合生化"
    assert report_after_related_change["lab_test_results"][0]["category_name"] == "综合生化"

    restored_related = client.patch(
        f"/api/account-settings/lab-dictionary/items/{renamed_item_id}",
        json={
            "item_name_zh": "丙氨酸氨基转移酶",
            "aliases": ["ALT", "谷丙转氨酶"],
            "description": None,
            "primary_category_name": "综合生化",
            "related_category_names": ["代谢相关"],
            "expected_dictionary_revision": dictionary["dictionary_revision"],
        },
    )
    assert restored_related.status_code == 200, restored_related.text
    dictionary = restored_related.json()["dictionary"]
    assert client.get(f"/api/members/{member_id('alice')}/reports/{report_id}").status_code == 200

    blocked_primary_delete = client.request(
        "DELETE",
        "/api/account-settings/lab-dictionary/categories/%E7%BB%BC%E5%90%88%E7%94%9F%E5%8C%96",
        json={"expected_dictionary_revision": dictionary["dictionary_revision"]},
    )
    assert blocked_primary_delete.status_code == 409
    assert blocked_primary_delete.json()["detail"]["code"] == "LAB_DICTIONARY_PRIMARY_CATEGORY_IN_USE"

    deleted_related = client.request(
        "DELETE",
        "/api/account-settings/lab-dictionary/categories/%E4%BB%A3%E8%B0%A2%E7%9B%B8%E5%85%B3",
        json={"expected_dictionary_revision": dictionary["dictionary_revision"]},
    )
    assert deleted_related.status_code == 200, deleted_related.text
    assert deleted_related.json()["effects"]["result_count"] == 0
    assert deleted_related.json()["effects"]["related_item_count"] == 1
    assert client.get(f"/api/members/{member_id('alice')}/reports/{report_id}").status_code == 200
    assert source_path.exists()


def test_lab_report_names_are_dictionary_managed(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    from backend.app.main import create_app
    from backend.app.repositories.report_repository import ReportRepository
    from backend.app.storage.paths import app_paths

    client = TestClient(create_app())
    _signup(client, "alice")
    repository = ReportRepository(account_id_for("alice"), app_paths())
    source_path = app_paths().report_attachment_path(
        account_id_for("alice"), "FILE-readonly", "txt"
    )
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("检验原件", encoding="utf-8")
    repository.register_source_file(
        member_id("alice"),
        resource_id="FILE-readonly",
        relative_path=str(source_path.relative_to(app_paths().account_root(account_id_for("alice")))),
        mime_type="text/plain",
        size_bytes=source_path.stat().st_size,
        sha256="readonly-source",
        source_kind="unknown",
    )
    report_id = repository.create_report(
        member_id("alice"),
        {
            "report_type": "检验报告",
            "report_name": "肾功能",
            "report_time": "2026-08-17",
            "lab_test_results": [
                {
                    "item_id": "item-creatinine",
                    "item_name_zh": "肌酐",
                    "category_name": "肾功能",
                    "result_text": "70 μmol/L",
                }
            ],
        },
        resource_id="FILE-readonly",
    )
    response = client.patch(
        f"/api/members/{member_id('alice')}/reports/{report_id}/fields",
        json={
            "field": "report_name",
            "value": "新名称",
        },
    )
    assert response.status_code == 400
    assert "检验指标分类目录" in response.json()["detail"]["message"]


def test_primary_category_change_merges_same_source_category_reports(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    from backend.app.main import create_app
    from backend.app.repositories.report_repository import ReportRepository
    from backend.app.storage.paths import app_paths

    client = TestClient(create_app())
    _signup(client, "alice")
    repository = ReportRepository(account_id_for("alice"), app_paths())
    source_path = app_paths().report_attachment_path(
        account_id_for("alice"), "FILE-reclassify", "txt"
    )
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("检验原件", encoding="utf-8")
    repository.register_source_file(
        member_id("alice"),
        resource_id="FILE-reclassify",
        relative_path=str(source_path.relative_to(app_paths().account_root(account_id_for("alice")))),
        mime_type="text/plain",
        size_bytes=source_path.stat().st_size,
        sha256="reclassify-source",
        source_kind="unknown",
    )
    inflammation_report_id = repository.create_report(
        member_id("alice"),
        {
            "report_type": "检验报告",
            "report_name": "炎症指标",
            "report_time": "2026-08-08T07:33:00+08:00",
            "lab_test_results": [
                {
                    "item_id": "item-crp",
                    "item_name_zh": "C-反应蛋白",
                    "category_name": "炎症指标",
                    "result_text": "1.3 mg/L",
                }
            ],
        },
        resource_id="FILE-reclassify",
    )
    cardiac_report_id = repository.create_report(
        member_id("alice"),
        {
            "report_type": "检验报告",
            "report_name": "心肌酶谱",
            "report_time": "2026-08-08T07:33:00+08:00",
            "lab_test_results": [
                {
                    "item_id": "item-ck",
                    "item_name_zh": "肌酸激酶",
                    "category_name": "心肌酶谱",
                    "result_text": "75 U/L",
                }
            ],
        },
        resource_id="FILE-reclassify",
    )
    dictionary = client.get("/api/account-settings/lab-dictionary").json()
    item = next(row for row in dictionary["items"] if row["item_name_zh"] == "C-反应蛋白")

    changed = client.patch(
        f"/api/account-settings/lab-dictionary/items/{item['item_id']}",
        json={
            "item_name_zh": item["item_name_zh"],
            "aliases": item["aliases"],
            "description": item["description"],
            "primary_category_name": "心肌酶谱",
            "related_category_names": [],
            "expected_dictionary_revision": dictionary["dictionary_revision"],
        },
    )

    assert changed.status_code == 200, changed.text
    assert changed.json()["effects"]["reclassified_result_count"] == 1
    assert changed.json()["effects"]["moved_to_existing_report_count"] == 1
    assert changed.json()["effects"]["deleted_report_count"] == 1
    assert client.get(f"/api/members/{member_id('alice')}/reports/{inflammation_report_id}").status_code == 404
    cardiac_report = client.get(f"/api/members/{member_id('alice')}/reports/{cardiac_report_id}").json()
    assert cardiac_report["report_name"] == "心肌酶谱"
    assert {
        (row["item_name_zh"], row["category_name"])
        for row in cardiac_report["lab_test_results"]
    } == {("C-反应蛋白", "心肌酶谱"), ("肌酸激酶", "心肌酶谱")}
    assert source_path.exists()
    assert client.get(f"/api/members/{member_id('alice')}/reports").json()["total"] == 1


def test_categories_are_flat_and_reject_hierarchy_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    from backend.app.main import create_app

    client = TestClient(create_app())
    _signup(client, "alice")
    dictionary = client.get("/api/account-settings/lab-dictionary").json()

    created = client.post(
        "/api/account-settings/lab-dictionary/categories",
        json={
            "category_name": "肝脏酶学",
            "description": "肝脏相关酶学指标",
            "expected_dictionary_revision": dictionary["dictionary_revision"],
        },
    )
    assert created.status_code == 200, created.text
    dictionary = created.json()["dictionary"]
    category = dictionary["categories"][0]
    assert category["category_name"] == "肝脏酶学"
    assert category["description"] == "肝脏相关酶学指标"
    assert "parent_id" not in category
    assert "level" not in category
    assert "child_count" not in category

    hierarchy_payload = client.post(
        "/api/account-settings/lab-dictionary/categories",
        json={
            "category_name": "旧层级分类",
            "parent_id": "肝脏酶学",
            "description": None,
            "expected_dictionary_revision": dictionary["dictionary_revision"],
        },
    )
    assert hierarchy_payload.status_code == 422

    removed = client.request(
        "DELETE",
        "/api/account-settings/lab-dictionary/categories/%E8%82%9D%E8%84%8F%E9%85%B6%E5%AD%A6",
        json={
            "expected_dictionary_revision": dictionary["dictionary_revision"],
        },
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["dictionary"]["categories"] == []

    missing_item = client.request(
        "DELETE",
        "/api/account-settings/lab-dictionary/items/missing",
        json={
            "expected_dictionary_revision": removed.json()["dictionary"][
                "dictionary_revision"
            ]
        },
    )
    assert missing_item.status_code == 404


def test_report_import_creates_server_owned_dictionary_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    from backend.app.main import create_app
    from backend.app.repositories.report_repository import ReportRepository
    from backend.app.storage.paths import app_paths

    client = TestClient(create_app())
    _signup(client, "alice")
    repository = ReportRepository(account_id_for("alice"), app_paths())
    source_path = app_paths().report_attachment_path(
        account_id_for("alice"), "FILE-import", "txt"
    )
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("检验原件", encoding="utf-8")
    repository.register_source_file(
        member_id("alice"),
        resource_id="FILE-import",
        relative_path=str(source_path.relative_to(app_paths().account_root(account_id_for("alice")))),
        mime_type="text/plain",
        size_bytes=source_path.stat().st_size,
        sha256="dictionary-source",
        source_kind="unknown",
    )
    created = repository.create_report_from_parsed(
        member_id("alice"),
        parsed_report={
            "report_type": "检验报告",
            "report_name": "电解质",
            "report_time": "2026-08-17T10:00:00+08:00",
            "institution_name": None,
            "lab_test_results": [
                {
                    "item_id": "item-sodium",
                    "item_name_zh": "血钠",
                    "aliases": ["Na"],
                    "category_name": "电解质",
                    "result_text": "140 mmol/L",
                    "reference_text": "137–147 mmol/L",
                    "flag_text": "正常",
                }
            ],
        },
        resource_ids=["FILE-import"],
    )
    detail = repository.get_report_detail(member_id("alice"), created["report_id"])
    dictionary = repository.lab_dictionary(member_id("alice"))
    assert detail is not None
    assert detail["lab_test_results"][0]["item_name_zh"] == "血钠"
    assert dictionary["summary"] == {
        "item_count": 1,
        "category_count": 1,
        "relation_count": 1,
    }
    assert "status" not in dictionary["items"][0]
    assert "status" not in dictionary["categories"][0]
    assert dictionary["items"][0]["item_name_zh"] == "血钠"
    assert dictionary["items"][0]["primary_category_name"] == "电解质"
    assert dictionary["items"][0]["related_category_names"] == []
