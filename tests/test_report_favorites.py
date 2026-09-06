from member_support import account_id as account_id_for, member_id
import os
import tempfile
from tests.api_client import TestClient


def test_favorite_list_returns_every_lightweight_summary_in_stable_order():
    from backend.app.storage.favorite_database import initialize_favorites_database as _init_favorites_db
    from backend.app.main import create_app
    from backend.app.storage.paths import app_paths
    from backend.app.storage.sqlite import connect

    client = TestClient(create_app())
    sign_up = client.post(
        "/api/auth/sign_up",
        json={
            "account": "alice",
            "account_name": "Alice",
            "password": "secret",
            "confirm_password": "secret",
        },
    )
    assert sign_up.status_code == 200
    member = member_id("alice")
    account_id = account_id_for("alice")
    _init_favorites_db(account_id)
    with connect(app_paths().favorites_db(account_id)) as connection:
        connection.executemany(
            """
            INSERT INTO favorites (
                favorite_id, member_id,
                source_type, source_session_id, source_id, title,
                content_snapshot, tags, created_at, updated_at
            ) VALUES (?, ?, 'message', ?, ?, ?, ?, '[]', ?, ?)
            """,
            [
                (
                    f"favorite-{index:03d}",
                    member,
                    f"session-{index:03d}",
                    f"message-{index:03d}",
                    f"收藏 {index}",
                    f"完整正文 {index}",
                    "2026-09-04T10:00:00+08:00",
                    "2026-09-04T10:00:00+08:00",
                )
                for index in range(51)
            ],
        )
    other_account_id = account_id_for("bob")
    _init_favorites_db(other_account_id)
    with connect(app_paths().favorites_db(other_account_id)) as connection:
        connection.execute(
            """
            INSERT INTO favorites (
                favorite_id, member_id,
                source_type, source_session_id, source_id, title,
                content_snapshot, tags, created_at, updated_at
            ) VALUES (
                'other-account', NULL, 'message',
                'other-session', 'other-message', '其它账号', '正文',
                '[]', '2026-09-05T10:00:00+08:00', '2026-09-05T10:00:00+08:00'
            )
            """
        )

    response = client.get("/api/favorites")
    assert response.status_code == 200
    body = response.json()
    assert len(body["favorites"]) == 51
    assert body["favorites"][0]["favorite_id"] == "favorite-050"
    assert body["favorites"][-1]["favorite_id"] == "favorite-000"
    assert body["favorites"][0]["content_summary"] == "完整正文 50"
    assert all("content_snapshot" not in favorite for favorite in body["favorites"])
    assert all(favorite["favorite_id"] != "other-account" for favorite in body["favorites"])
    assert body["has_more"] is False
    assert body["next_cursor"] is None




def test_report_favorite_targets_report_without_requiring_analysis():
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
                "report_type": "其它报告",
                "report_name": "肺功能检查",
                "report_time": "2026-08-20T09:30:00+08:00",
                "institution_name": "示例医院",
                "other_report": {"report_body": "FEV1 为 2.31 L。"},
            },
        )
        assert created.status_code == 201, created.text
        report = created.json()
        assert report["has_analysis"] is False

        favorite = client.post(
            "/api/favorites",
            json={"source_type": "report", "member_id": member_id("alice"), "source_id": report["report_id"]},
        )
        assert favorite.status_code == 200, favorite.text
        body = favorite.json()
        assert body["source_type"] == "report"
        assert body["source_id"] == report["report_id"]
        assert body["title"] == "其它报告 - 肺功能检查"
        assert "FEV1 为 2.31 L。" in body["content_snapshot"]
        assert "示例医院" in body["content_snapshot"]
        assert "解读结果" not in body["content_snapshot"]
        assert body["source_available"] is True

        duplicate = client.post(
            "/api/favorites",
            json={"source_type": "report", "member_id": member_id("alice"), "source_id": report["report_id"]},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["message"] == "该报告已收藏。"

        for unsupported_source_type in (
            "report_analysis",
            "_".join(("report", "qa")),
        ):
            unsupported_favorite = client.post(
                "/api/favorites",
                json={
                    "source_type": unsupported_source_type,
                    "source_id": report["report_id"],
                },
            )
            assert unsupported_favorite.status_code == 400
            assert unsupported_favorite.json()["detail"]["code"] == "INVALID_REQUEST"

        deleted = client.delete(f"/api/members/{member_id('alice')}/reports/{report['report_id']}")
        assert deleted.status_code == 200, deleted.text
        retained = client.get(f"/api/favorites/{body['favorite_id']}")
        assert retained.status_code == 200
        assert retained.json()["source_available"] is False
        assert "FEV1 为 2.31 L。" in retained.json()["content_snapshot"]

        analyzed_report = client.post(
            f"/api/members/{member_id('alice')}/reports",
            json={
                "report_type": "检查报告",
                "report_name": "胸部 CT",
                "report_time": "2026-08-21T10:00:00+08:00",
                "examination_report": {
                    "exam_name": "胸部 CT",
                    "exam_findings": "双肺纹理清晰。",
                    "exam_diagnosis": "未见明显异常。",
                },
            },
        ).json()
        analyzed_report = client.patch(
            f"/api/members/{member_id('alice')}/reports/{analyzed_report['report_id']}/fields",
            json={
                "field": "analysis_content",
                "value": "整体未见明显异常，结合症状随访。",
            },
        ).json()
        analyzed_favorite = client.post(
            "/api/favorites",
            json={
                "source_type": "report", "member_id": member_id("alice"),
                "source_id": analyzed_report["report_id"],
            },
        )
        assert analyzed_favorite.status_code == 200, analyzed_favorite.text
        analyzed_snapshot = analyzed_favorite.json()["content_snapshot"]
        assert "## 检查结果" in analyzed_snapshot
        assert "双肺纹理清晰。" in analyzed_snapshot
        assert "## 解读结果" in analyzed_snapshot
        assert "整体未见明显异常，结合症状随访。" in analyzed_snapshot
    finally:
        directory.cleanup()
        if previous is None:
            os.environ.pop("DATA_ROOT", None)
        else:
            os.environ["DATA_ROOT"] = previous
