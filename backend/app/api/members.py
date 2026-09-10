from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.api.dependencies import require_current_user
from backend.app.application.auth_service import CurrentUser
from backend.app.application.member_service import MemberService


router = APIRouter(tags=["members"])


class MemberFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    member_name: str = Field(min_length=1, max_length=80)
    sex: Literal["male", "female", "other"] | None = None
    birth_date: date | None = None
    blood_type: Literal["a", "b", "ab", "o", "other"] | None = None

    @field_validator("member_name", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("birth_date")
    @classmethod
    def past_birth_date(cls, value):
        if value and value > date.today():
            raise ValueError("出生日期不能晚于今天。")
        return value


class MemberSaveRequest(MemberFields):
    set_as_default: bool = False


class PreferencesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    startup_mode: Literal["default", "last_used"] | None = None
    last_member_id: str | None = None
    default_member_id: str | None = Field(default=None, min_length=1)

    @field_validator("default_member_id", mode="before")
    @classmethod
    def nonempty_default(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("默认成员不能为空。")
        return value.strip()

    @field_validator("last_member_id", mode="before")
    @classmethod
    def normalize_last_member(cls, value):
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("最近选择的成员标识无效。")
        return value.strip()


class GrantEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    member_id: str
    permission: Literal["read", "edit"]


class GrantsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grantee_account: str
    grants: list[GrantEntry] = Field(min_length=1, max_length=100)


def member_service(request: Request) -> MemberService:
    return request.app.state.services.member_service


@router.get("/api/members")
def list_members(user: CurrentUser = Depends(require_current_user), service: MemberService = Depends(member_service)):
    return service.list_members(user.account_id)


@router.post("/api/members", status_code=201)
def create_member(payload: MemberSaveRequest, user: CurrentUser = Depends(require_current_user), service: MemberService = Depends(member_service)):
    return service.create_member(user.account_id, payload.model_dump(mode="json", exclude={"set_as_default"}), set_as_default=payload.set_as_default)


@router.patch("/api/account-settings/member-preferences")
def save_preferences(payload: PreferencesRequest, user: CurrentUser = Depends(require_current_user), service: MemberService = Depends(member_service)):
    return service.preferences(
        user.account_id,
        **{name: getattr(payload, name) for name in payload.model_fields_set},
    )


@router.get("/api/members/access-events")
async def access_events(request: Request, user: CurrentUser = Depends(require_current_user), service: MemberService = Depends(member_service)):
    async def events():
        previous = None
        # Bound the otherwise permanent stream so graceful server restarts can
        # finish. EventSource reconnects and the client rechecks all permissions.
        deadline = asyncio.get_running_loop().time() + 30
        while asyncio.get_running_loop().time() < deadline and not await request.is_disconnected():
            revision = await asyncio.to_thread(service.access_revision, user.account_id)
            if revision != previous:
                yield f"id: {revision}\nevent: member_access\ndata: {json.dumps({'revision': revision})}\n\n"
                previous = revision
            else:
                yield ": keep-alive\n\n"
            await asyncio.sleep(2)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})


@router.get("/api/members/{member_id}")
def get_member(member_id: str, user: CurrentUser = Depends(require_current_user), service: MemberService = Depends(member_service)):
    return service.get_member(user.account_id, member_id)


@router.patch("/api/members/{member_id}")
def update_member(member_id: str, payload: MemberSaveRequest, user: CurrentUser = Depends(require_current_user), service: MemberService = Depends(member_service)):
    return service.update_member(user.account_id, member_id, payload.model_dump(mode="json", exclude={"set_as_default"}), set_as_default=payload.set_as_default)


@router.delete("/api/members/{member_id}")
def delete_member(member_id: str, user: CurrentUser = Depends(require_current_user), service: MemberService = Depends(member_service)):
    return service.delete_member(user.account_id, member_id)


@router.get("/api/members/{member_id}/lab-dictionary")
def read_member_dictionary(request: Request, member_id: str, user: CurrentUser = Depends(require_current_user)):
    return request.app.state.services.report(user.account_id, member_id).member_lab_dictionary(member_id)


@router.get("/api/account-settings/member-grants")
def list_grants(user: CurrentUser = Depends(require_current_user), service: MemberService = Depends(member_service)):
    return service.grants(user.account_id)


@router.put("/api/account-settings/member-grants")
def set_grants(payload: GrantsRequest, user: CurrentUser = Depends(require_current_user), service: MemberService = Depends(member_service)):
    return service.set_grants(user.account_id, payload.grantee_account, [item.model_dump() for item in payload.grants])


@router.delete("/api/account-settings/member-grants/{member_id}/{account_id}")
def revoke_grant(member_id: str, account_id: str, user: CurrentUser = Depends(require_current_user), service: MemberService = Depends(member_service)):
    return service.revoke(user.account_id, member_id, account_id)


from backend.app.schemas.medical_history import MedicalHistoryField, MedicalHistoryUpdate


@router.get("/api/members/{member_id}/medical-history")
def read_medical_history(request: Request, member_id: str, fields: list[MedicalHistoryField] | None = Query(default=None), user: CurrentUser = Depends(require_current_user)):
    return request.app.state.services.medical_history.read(user.account_id, member_id, fields)


@router.patch("/api/members/{member_id}/medical-history")
def update_medical_history(request: Request, member_id: str, payload: MedicalHistoryUpdate, user: CurrentUser = Depends(require_current_user)):
    return request.app.state.services.medical_history.update(user.account_id, member_id, payload.model_dump(exclude_unset=True))
