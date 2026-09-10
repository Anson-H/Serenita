"""Fixtures mounted only by the isolated integration server, never production."""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import APIRouter
from backend.app.application.auth_service import AuthService
from backend.app.repositories.notification_repository import timestamp
from backend.app.storage.sqlite import connect


def install(app):
    service = app.state.services
    router = APIRouter(prefix="/integration/notifications")
    state = {}

    async def no_recovery():
        await asyncio.Future()

    # The entire latency acceptance runs with periodic recovery disabled.
    service.notification_scheduler.recovery = no_recovery

    @router.post("/seed")
    def seed():
        owner = service.auth.repository.account_by_login("integration")["account_id"]
        member = service.members.create(owner, {"member_name": "通知延迟验收"})
        actors = [owner]
        for n in range(1, 10):
            name = f"notification{n}"
            user, _ = AuthService(paths=service.paths).sign_up(
                account=name,
                account_name=name,
                password="test-password",
                confirm_password="test-password",
            )
            actors.append(user.account_id)
            service.members.set_grants(
                owner, name, [{"member_id": member, "permission": "read"}]
            )
        for actor in actors:
            service.notifications.set_preferences(actor, True)
        medication = service.medications.save(
            owner,
            member,
            "medication",
            {"generic_name": "验收药品"},
            request_id=str(uuid4()),
        )
        now = datetime.now(timezone.utc)
        plans = []
        for n in range(100):
            plans.append(
                service.medications.save(
                    owner,
                    member,
                    "plan",
                    {
                        "medication_id": medication["medication_id"],
                        "starts_at": timestamp(
                            (now - timedelta(days=1)).replace(second=0, microsecond=0)
                        ),
                        "start_precision": "minute",
                        "timezone": "UTC",
                        "dose_text": "1 片",
                        "schedule": {
                            "kind": "daily",
                            "times": [
                                {"time": (now + timedelta(hours=12)).strftime("%H:%M")}
                            ],
                        },
                    },
                    request_id=str(uuid4()),
                )
            )
        state.update(owner=owner, member=member, actors=actors, plans=plans)
        return {"member_id": member, "accounts": 10, "plans_per_account": 100}

    @router.post("/arm")
    def arm():
        now = datetime.now(timezone.utc)
        due = (now + timedelta(seconds=65)).replace(second=0, microsecond=0)
        for plan in state["plans"][:5]:
            service.medications.save(
                state["owner"],
                state["member"],
                "plan",
                {
                    "schedule": {
                        "kind": "daily",
                        "times": [{"time": due.strftime("%H:%M")}],
                    },
                },
                object_id=plan["medication_plan_id"],
            )
        return {"due": timestamp(due), "simultaneous_notifications": 50}

    @router.post("/answer")
    def answer():
        from concurrent.futures import ThreadPoolExecutor
        from backend.app.application.conversations.service import ConversationService
        from tests.model_support import ConversationModelCatalog

        def generate(actor):
            chat = ConversationService(model_catalog=ConversationModelCatalog(), services=service)
            queued = chat.send_message(actor, None, "通知验收问题", "model_1", "default", [], member_id=None)
            chat.start_turn_job(actor, queued["session_id"], queued["stream_id"])
            chat.wait_for_turn_job(actor, queued["session_id"], queued["stream_id"], timeout=10)
            if chat.repository.turn_row(actor, queued["session_id"], queued["turn_id"])["status"] != "completed":
                raise RuntimeError("验收回答未完成")
            return queued["session_id"]

        with ThreadPoolExecutor(max_workers=10) as pool:
            sessions = list(pool.map(generate, state["actors"]))
        return {"saved_at": timestamp(), "sessions": sessions}

    @router.get("/records")
    def records():
        records = []
        for actor in state["actors"]:
            records.extend(service.notifications.repository.rows(actor, limit=500))
        return {"records": records}

    app.include_router(router)
