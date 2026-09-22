from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GenerationRequest(StrictRequest):
    model_id: str
    request: dict[str, Any]
    thinking_mode: str = "default"
    stream: bool = False
    timeout_seconds: float | None = Field(default=None, gt=0, le=3600)
    attempt: int = Field(default=1, ge=1, le=10)


class EmbeddingRequest(StrictRequest):
    model_id: str
    inputs: list[dict[str, Any]] = Field(min_length=1)
    mode: Literal["independent", "fusion"] = "independent"
    dimensions: int | None = Field(default=None, gt=0)
    timeout_seconds: float | None = Field(default=None, gt=0, le=3600)
    purpose: str = "embedding"
    attempt: int = Field(default=1, ge=1, le=10)


class DeviceAuthorizationRequest(StrictRequest):
    client_id: Literal["serenita-self-hosted"]
    scope: Literal["models:read models:invoke"] = "models:read models:invoke"
    client_name: str = Field(default="Serenita 自部署", min_length=1, max_length=100)


class DeviceDecisionRequest(StrictRequest):
    user_code: str
    approve: bool


class DeviceTokenRequest(StrictRequest):
    device_code: str
    client_id: Literal["serenita-self-hosted"]
    grant_type: Literal["urn:ietf:params:oauth:grant-type:device_code"]


class OnboardingRequest(StrictRequest):
    choice: Literal["serenita", "own_api", "later"]


class DeviceRequestReference(StrictRequest):
    user_code: str = Field(min_length=1, max_length=100)


class DeviceCancelRequest(StrictRequest):
    device_code: str
    client_id: Literal["serenita-self-hosted"]


class DeviceSignInRequest(DeviceRequestReference):
    account: str
    password: str


class DeviceSignUpRequest(DeviceSignInRequest):
    account_name: str
    confirm_password: str
