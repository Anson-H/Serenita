from backend.app.providers.model_type_probe import detect_model_type, probe_embeddings
from backend.app.core.model_probe_tasks import probes_for_paths
from backend.app.storage.paths import app_paths
from backend.app.application.provider_errors import raise_provider_error
from typing import Any
from backend.app.core.cancellation import CancellationToken, OperationCancelledError
from backend.app.core.errors import raise_error
from backend.app.core.time import local_now_iso as now_iso
from backend.app.domain.model_capabilities import (
    EmbeddingCapabilities,
    eligible_for_default,
    DEFAULT_CAPABILITY_PROFILE,
    MODEL_DEFAULT_PURPOSES,
    ModelCapabilityProfiles,
    ModelCapabilityProfile,
    ModelModeCapabilityProfile,
    capability_profiles_from_mapping,
    capability_response,
    profiles_from_profile,
)
from backend.app.storage.model_codec import (
    capability_profiles_from_row,
    profile_from_row,
)
from backend.app.providers.base import ModelProvider
from backend.app.providers.capability_probe import THINKING_MODE_PROBE_ORDER
from backend.app.providers.errors import (
    ProviderChatCompletionError,
    ProviderModelListError,
)
from backend.app.providers.types import ProviderModel
from backend.app.providers.default_registry import create_default_provider_registry
from backend.app.providers.registry import ProviderNotFoundError
from backend.app.storage.provider_secrets import (
    provider_secret_from_row,
    sealed_provider_secret,
)
from backend.app.schemas.model_provider import (
    ModelProviderSaveRequest,
    ModelProviderPatchRequest,
    ModelProviderTestRequest,
    AddModelRequest,
    ModelPatchRequest,
    ModelDefaultsPatchRequest,
)
from backend.app.storage.model_codec import model_response
from backend.app.repositories.model_provider_repository import ModelProviderRepository


def _model_payload_from_provider_model(model: ProviderModel) -> dict[str, Any]:
    return {
        "remote_model_id": model.remote_model_id,
        "model_name": model.model_name,
        "created_at": model.created_at,
        "model_type": model.model_type,
        "embedding_capabilities": None, "embedding_dimensions": None, "max_input_tokens": None, "max_batch_size": None,
        **capability_response(model.capability_profile()),
    }


def _probe_metadata_baseline(
    *,
    remote_model: ProviderModel | None,
    metadata_result: dict,
    current_profile: ModelCapabilityProfile,
    current_profiles: ModelCapabilityProfiles,
) -> tuple[ModelCapabilityProfile, ModelCapabilityProfiles, dict[str, str], dict[str, bool]]:
    if remote_model is None:
        return current_profile, current_profiles, metadata_result, {}
    listed_profile = remote_model.capability_profile()
    declarations = dict(remote_model.capability_declarations)
    metadata_profile = ModelCapabilityProfile(
        supports_text=listed_profile.supports_text
        if "text" in declarations
        else current_profile.supports_text,
        file_mime_types=_merge_declared_file_mime_types(
            current_profile.file_mime_types,
            listed_profile.file_mime_types,
            declarations,
        ),
        thinking_modes=listed_profile.thinking_modes
        if "thinking" in declarations
        else current_profile.thinking_modes,
        supports_tool_calling=listed_profile.supports_tool_calling
        if "tool_calling" in declarations
        else current_profile.supports_tool_calling,
        default_thinking_state=listed_profile.default_thinking_state
        if "thinking" in declarations
        else current_profile.default_thinking_state,
        context_window_tokens=current_profile.context_window_tokens
        if current_profile.context_window_tokens is not None
        else listed_profile.context_window_tokens,
        max_output_tokens=current_profile.max_output_tokens
        if current_profile.max_output_tokens is not None
        else listed_profile.max_output_tokens,
    )
    def merge_state(current):
        return ModelModeCapabilityProfile(
            availability=current.availability,
            supports_text=listed_profile.supports_text if "text" in declarations else current.supports_text,
            file_mime_types=_merge_declared_file_mime_types(
                current.file_mime_types, listed_profile.file_mime_types, declarations,
            ),
            supports_tool_calling=listed_profile.supports_tool_calling
            if "tool_calling" in declarations else current.supports_tool_calling,
        )

    return (
        metadata_profile,
        ModelCapabilityProfiles(
            default_state=metadata_profile.default_thinking_state if "thinking" in declarations else current_profiles.default_state,
            non_thinking=merge_state(current_profiles.non_thinking),
            thinking=merge_state(current_profiles.thinking),
        ),
        {"status": "refreshed", "message": "已刷新供应商元数据。"},
        declarations,
    )


def _merge_declared_file_mime_types(
    current: list[str], listed: list[str], declarations: dict[str, bool]
) -> list[str]:
    merged: list[str] = []
    for capability, predicate in (
        ("image_input", lambda mime_type: mime_type.startswith("image/")),
        ("pdf_input", lambda mime_type: mime_type == "application/pdf"),
        ("audio_input", lambda mime_type: mime_type.startswith("audio/")),
        ("video_input", lambda mime_type: mime_type.startswith("video/")),
    ):
        source = listed if capability in declarations else current
        merged.extend((mime_type for mime_type in source if predicate(mime_type)))
    return list(dict.fromkeys(merged))


def _profile_with_probed_thinking_modes(
    profile: ModelCapabilityProfile,
    profiles: ModelCapabilityProfiles,
    thinking_mode_checks: dict[str, str],
) -> ModelCapabilityProfile:
    current_modes = set(profile.thinking_modes)
    thinking_modes = [
        "default",
        *[
            mode
            for mode in THINKING_MODE_PROBE_ORDER
            if thinking_mode_checks.get(mode) == "supported"
            or (
                thinking_mode_checks.get(mode) == "unverified" and mode in current_modes
            )
        ],
    ]
    return ModelCapabilityProfile(
        supports_text=profile.supports_text,
        file_mime_types=list(profile.file_mime_types),
        thinking_modes=thinking_modes,
        supports_tool_calling=profile.supports_tool_calling,
        default_thinking_state=profiles.default_state,
        context_window_tokens=profile.context_window_tokens,
        max_output_tokens=profile.max_output_tokens,
    )


def _normalized_string_list(values: list[str], *, field_name: str) -> list[str]:
    normalized: list[str] = []
    for value in values:
        item = value.strip()
        if not item:
            raise_error(
                "invalid_structure",
                "INVALID_MODEL_CAPABILITY",
                f"{field_name} 不能包含空值。",
            )
        if item not in normalized:
            normalized.append(item)
    return normalized


class ModelSettingsService:
    def __init__(self, repository=None, provider_registry=None, *, paths=None):
        self.paths = paths or getattr(repository, "paths", None) or app_paths()
        self.repository = repository or ModelProviderRepository(paths=self.paths)
        self.probes = probes_for_paths(self.paths)
        self.provider_registry = provider_registry

    def _registry_provider(self, provider_id: str) -> ModelProvider:
        registry = self.provider_registry or create_default_provider_registry()
        try:
            return registry.get(provider_id)
        except ProviderNotFoundError:
            raise_error("missing", "NOT_FOUND", "模型服务不存在。")

    def _provider_row(self, account_id: str, provider_id: str):
        with self.repository.transaction(account_id) as connection:
            return connection.get_provider(provider_id=provider_id)

    def _provider_public_row(self, account_id: str, provider_id: str):
        with self.repository.transaction(account_id) as connection:
            return connection.get_public_provider(provider_id=provider_id)

    def _provider_summary(
        self, account_id: str, provider: ModelProvider
    ) -> dict[str, Any]:
        row = self._provider_public_row(account_id, provider.provider_id)
        return {
            "provider_id": provider.provider_id,
            "provider_name": provider.provider_name,
            "default_api_url": provider.default_api_url,
            "default_official_url": provider.default_official_url,
            "native_attachment_mime_types": sorted(
                provider.native_attachment_mime_types()
            ),
            "api_url": row["api_url"] if row else provider.default_api_url,
            "official_url": row["official_url"]
            if row and row["official_url"] is not None
            else provider.default_official_url,
            "has_api_key": bool(row["has_api_key"]) if row else False,
            "is_configured": bool(row["is_configured"]) if row else False,
        }

    def _api_key_from_row(self, account_id: str, row) -> str:
        return provider_secret_from_row(account_id, row, paths=self.paths)

    def _saved_api_key(self, account_id: str, provider_id: str) -> str:
        return self._api_key_from_row(
            account_id, self._provider_row(account_id, provider_id)
        )

    def _default_model_row(self, connection, purpose: str):
        return connection.default_model(purpose)

    def _set_model_default_in_connection(
        self, connection, purpose: str, model_id: str | None
    ) -> None:
        connection.set_default(purpose, model_id=model_id)

    def _model_defaults_response(self, account_id: str) -> dict[str, Any]:
        with self.repository.transaction(account_id) as connection:
            defaults = {}
            for purpose in MODEL_DEFAULT_PURPOSES:
                row = self._default_model_row(connection, purpose)
                defaults[purpose] = model_response(row) if row else None
        return {"defaults": defaults}

    def _write_model_profile(
        self,
        connection,
        row,
        *,
        model_name: str,
        profile: ModelCapabilityProfile,
        profiles: ModelCapabilityProfiles,
    ):
        connection.write_profile(
            model_name=model_name,
            updated_at=now_iso(),
            profile=profile,
            profiles=profiles,
            model_id=row["model_id"],
        )
        return connection.get_model(model_id=row["model_id"])

    def list_model_providers(self, account_id: str):
        registry = self.provider_registry or create_default_provider_registry()
        return {
            "providers": [
                self._provider_summary(account_id, provider)
                for provider in registry.providers()
            ]
        }

    def reveal_model_provider_credential(self, account_id: str, provider_id: str):
        provider = self._registry_provider(provider_id)
        api_key = self._saved_api_key(account_id, provider.provider_id)
        if not api_key:
            raise_error(
                "missing", "MODEL_NOT_CONFIGURED", "该模型服务尚未配置 API key。"
            )
        return {"provider_id": provider.provider_id, "api_key": api_key}

    def create_model_provider(self, account_id: str, payload: ModelProviderSaveRequest):
        provider = self._registry_provider(payload.provider_id)
        existing = self._provider_row(account_id, provider.provider_id)
        submitted_key = payload.api_key.strip() if payload.api_key else ""
        sealed_key = (
            sealed_provider_secret(
                account_id, provider.provider_id, submitted_key, paths=self.paths
            )
            if submitted_key
            else existing["encrypted_api_key"]
            if existing and existing["encrypted_api_key"]
            else None
        )
        api_url = (
            payload.api_url
            if payload.api_url is not None
            else existing["api_url"]
            if existing
            else provider.default_api_url
        )
        official_url = (
            payload.official_url
            if payload.official_url is not None
            else existing["official_url"]
            if existing and existing["official_url"] is not None
            else provider.default_official_url
        )
        timestamp = now_iso()
        with self.repository.transaction(account_id, write=True) as connection:
            connection.save_provider(
                provider_id=provider.provider_id,
                provider_name=provider.provider_name,
                api_url=api_url or provider.default_api_url,
                official_url=official_url,
                encrypted_api_key=sealed_key,
                is_configured=1 if sealed_key else 0,
                created_at=timestamp,
                updated_at=timestamp,
            )
        return self._provider_summary(account_id, provider)

    def update_model_provider(
        self, account_id: str, provider_id: str, payload: ModelProviderPatchRequest
    ):
        provider = self._registry_provider(provider_id)
        existing = self._provider_row(account_id, provider_id)
        if not existing:
            raise_error("missing", "NOT_FOUND", "该模型服务尚未配置。")
        next_api_url = (
            payload.api_url if payload.api_url is not None else existing["api_url"]
        )
        next_official_url = (
            payload.official_url
            if payload.official_url is not None
            else existing["official_url"]
            if existing["official_url"] is not None
            else provider.default_official_url
        )
        submitted_key = payload.api_key.strip() if payload.api_key else ""
        next_sealed_key = (
            sealed_provider_secret(
                account_id, provider.provider_id, submitted_key, paths=self.paths
            )
            if submitted_key
            else existing["encrypted_api_key"]
        )
        timestamp = now_iso()
        with self.repository.transaction(account_id, write=True) as connection:
            connection.update_provider(
                api_url=next_api_url or provider.default_api_url,
                official_url=next_official_url,
                encrypted_api_key=next_sealed_key,
                is_configured=1 if next_sealed_key else 0,
                updated_at=timestamp,
                provider_id=provider_id,
            )
        return self._provider_summary(account_id, provider)

    def test_model_provider(
        self, account_id: str, provider_id: str, payload: ModelProviderTestRequest
    ):
        provider = self._registry_provider(provider_id)
        api_key = (payload.api_key or "").strip() or self._saved_api_key(
            account_id, provider_id
        )
        if not api_key:
            raise_error(
                "invalid_structure", "MODEL_NOT_CONFIGURED", "请先输入或保存 API key。"
            )
        saved_provider = self._provider_row(account_id, provider_id)
        result = provider.test_connection(
            api_url=payload.api_url
            or (saved_provider["api_url"] if saved_provider else None)
            or provider.default_api_url,
            api_key=api_key,
        )
        if not result.reachable:
            raise_provider_error(
                ProviderModelListError(
                    result.message, code=result.code or "MODEL_ERROR"
                )
            )
        return {
            "provider_id": result.provider_id,
            "reachable": result.reachable,
            "message": result.message,
        }

    def list_remote_models(self, account_id: str, provider_id: str):
        provider = self._registry_provider(provider_id)
        row = self._provider_row(account_id, provider_id)
        if not row or not row["is_configured"]:
            raise_error(
                "invalid_structure", "MODEL_NOT_CONFIGURED", "请先配置该模型服务。"
            )
        api_key = self._saved_api_key(account_id, provider_id)
        if not api_key:
            raise_error(
                "invalid_structure", "MODEL_NOT_CONFIGURED", "请先输入或保存 API key。"
            )
        try:
            remote_models = provider.list_models(
                api_url=row["api_url"] or provider.default_api_url, api_key=api_key
            )
        except ProviderModelListError as exc:
            raise_provider_error(exc)
        return {
            "provider_id": provider.provider_id,
            "models": [
                _model_payload_from_provider_model(model) for model in remote_models
            ],
        }

    def add_model(self, account_id: str, payload: AddModelRequest):
        self._registry_provider(payload.provider_id)
        provider_row = self._provider_row(account_id, payload.provider_id)
        if not provider_row or not provider_row["is_configured"]:
            raise_error(
                "invalid_structure", "MODEL_NOT_CONFIGURED", "请先配置该模型服务。"
            )
        if not payload.remote_model_id.strip():
            raise_error("invalid_structure", "INVALID_MODEL_ID", "模型 ID 不能为空。")
        model_id = f"{payload.provider_id}:{payload.remote_model_id}"
        model_name = payload.remote_model_id
        timestamp = now_iso()
        with self.repository.transaction(account_id, write=True) as connection:
            connection.save_model(
                model_id=model_id,
                provider_id=payload.provider_id,
                remote_model_id=payload.remote_model_id,
                model_name=model_name,
                created_at=timestamp,
                updated_at=timestamp,
            )
            row = connection.get_model(model_id=model_id)
        return model_response(row)

    def list_models(self, account_id: str):
        with self.repository.transaction(account_id) as connection:
            rows = connection.list_models()
        return {"models": [model_response(row) for row in rows]}

    def update_model(self, account_id: str, model_id: str, payload: ModelPatchRequest):
        with self.repository.transaction(account_id, write=True) as connection:
            row = connection.get_model(model_id=model_id)
            if not row:
                raise_error("missing", "MODEL_NOT_FOUND", "模型不存在或未添加。")
            self.probes.cancel(account_id, model_id)
            supplied = payload.model_fields_set
            model_type = payload.model_type if "model_type" in supplied else row["model_type"]
            if model_type is None:
                raise_error("invalid_structure", "INVALID_MODEL_TYPE", "模型类型不能为空。")
            if model_type != "generation":
                if any(getattr(payload, key) is not None for key in supplied & {"thinking_modes", "capability_profiles", "context_window_tokens", "max_output_tokens"}):
                    raise_error("invalid_structure", "INVALID_MODEL_CAPABILITY", "当前类型不使用生成模型参数。")
                if model_type != "embedding" and any(getattr(payload, key) is not None for key in supplied & {"embedding_capabilities", "embedding_dimensions", "max_input_tokens", "max_batch_size"}):
                    raise_error("invalid_structure", "INVALID_MODEL_CAPABILITY", "未确认类型不使用向量参数。")
                name = payload.model_name.strip() if payload.model_name is not None else row["model_name"]
                if not name or ("model_name" in supplied and payload.model_name is None):
                    raise_error("invalid_structure", "INVALID_MODEL_NAME", "模型名称不能为空。")
                existing = model_response(row)
                caps = payload.embedding_capabilities.model_dump() if payload.embedding_capabilities else existing["embedding_capabilities"] or EmbeddingCapabilities().model_dump()
                connection.write_typed_model(model_id=model_id, model_type=model_type, model_name=name,
                    embedding_capabilities=caps,
                    **{key: getattr(payload, key) if key in supplied else row[key] for key in ("embedding_dimensions", "max_input_tokens", "max_batch_size")}, updated_at=now_iso())
                updated_row = connection.get_model(model_id=model_id)
                cleared = self._reconcile_defaults(connection, updated_row, auto_chat=False)
                return {**model_response(updated_row), "cleared_defaults": cleared}
            if any(getattr(payload, key) is not None for key in supplied & {"embedding_capabilities", "embedding_dimensions", "max_input_tokens", "max_batch_size"}):
                raise_error("invalid_structure", "INVALID_MODEL_CAPABILITY", "生成模型不使用向量参数。")
            if row["model_type"] != "generation":
                initial_profile = ModelCapabilityProfile(thinking_modes=payload.thinking_modes or ["default"])
                connection.write_typed_model(model_id=model_id, model_type="generation", model_name=row["model_name"], profile=initial_profile, profiles=profiles_from_profile(initial_profile), updated_at=now_iso())
                row = connection.get_model(model_id=model_id)
            current = profile_from_row(row)
            current_profiles = capability_profiles_from_row(row)
            supplied = payload.model_fields_set
            non_nullable_fields = {
                "model_name",
                "thinking_modes",
                "capability_profiles",
            }
            if any(
                (
                    getattr(payload, field_name) is None
                    for field_name in supplied & non_nullable_fields
                )
            ):
                raise_error(
                    "invalid_structure",
                    "INVALID_MODEL_CAPABILITY",
                    "模型名称和能力字段不能为 null。",
                )
            model_name = (
                payload.model_name.strip()
                if "model_name" in supplied and payload.model_name is not None
                else row["model_name"]
            )
            if not model_name:
                raise_error(
                    "invalid_structure", "INVALID_MODEL_NAME", "模型名称不能为空。"
                )
            profiles = current_profiles
            if (
                "capability_profiles" in supplied
                and payload.capability_profiles is not None
            ):
                profile_payload = payload.capability_profiles.model_dump()
                provider = self._registry_provider(row["provider_id"])
                for state in ("non_thinking", "thinking"):
                    mode_payload = profile_payload[state]
                    normalized_types = _normalized_string_list(
                        mode_payload["file_mime_types"], field_name="附件类型"
                    )
                    unsupported_types = sorted(
                        set(normalized_types) - provider.native_attachment_mime_types()
                    )
                    if unsupported_types:
                        raise_error(
                            "invalid_structure",
                            "UNSUPPORTED_ATTACHMENT_TYPE",
                            f"当前模型服务不支持这些附件类型：{', '.join(unsupported_types)}。",
                        )
                    mode_payload["file_mime_types"] = normalized_types
                profiles = capability_profiles_from_mapping(
                    profile_payload, current_profiles
                )
            thinking_modes = current.thinking_modes
            if "thinking_modes" in supplied and payload.thinking_modes is not None:
                thinking_modes = _normalized_string_list(
                    payload.thinking_modes, field_name="思考档位"
                )
                if not thinking_modes:
                    raise_error(
                        "invalid_structure",
                        "INVALID_THINKING_MODES",
                        "至少保留一个思考档位。",
                    )
                allowed_thinking_modes = {
                    "default",
                    "off",
                    "minimal",
                    "low",
                    "medium",
                    "high",
                    "xhigh",
                    "max",
                }
                invalid_modes = sorted(set(thinking_modes) - allowed_thinking_modes)
                if invalid_modes:
                    raise_error(
                        "invalid_structure",
                        "INVALID_THINKING_MODES",
                        f"不支持这些思考档位：{', '.join(invalid_modes)}。",
                    )
            for field_name in ("context_window_tokens", "max_output_tokens"):
                value = getattr(payload, field_name)
                if field_name in supplied and value is not None and (value <= 0):
                    raise_error(
                        "invalid_structure",
                        "INVALID_MODEL_LIMIT",
                        "Token 上限必须为正整数或留空。",
                    )
            profile = ModelCapabilityProfile(
                thinking_modes=thinking_modes,
                default_thinking_state=profiles.default_state,
                context_window_tokens=payload.context_window_tokens
                if "context_window_tokens" in supplied
                else current.context_window_tokens,
                max_output_tokens=payload.max_output_tokens
                if "max_output_tokens" in supplied
                else current.max_output_tokens,
            )
            updated_row = self._write_model_profile(
                connection,
                row,
                model_name=model_name,
                profile=profile,
                profiles=profiles,
            )
            cleared = self._reconcile_defaults(connection, updated_row)
        return {**model_response(updated_row), "cleared_defaults": cleared}

    def _reconcile_defaults(self, connection, row, *, auto_chat=True):
        model = model_response(row)
        cleared = []
        for purpose in MODEL_DEFAULT_PURPOSES:
            current = connection.default_model(purpose)
            if current and current["model_id"] == row["model_id"] and not eligible_for_default(model, purpose):
                connection.set_default(purpose, model_id=None)
                cleared.append(purpose)
        if auto_chat and eligible_for_default(model, "chat") and not connection.default_model("chat"):
            connection.set_default("chat", model_id=row["model_id"])
        return cleared

    def probe_model_capabilities(self, account_id: str, model_id: str, probe_id: str | None = None):
        cancellation_token = self.probes.begin(account_id, model_id, probe_id)
        try:
            with self.repository.transaction(account_id) as connection:
                model_row = connection.get_model(model_id=model_id)
            if not model_row:
                raise_error("missing", "MODEL_NOT_FOUND", "模型不存在或未添加。")
            provider = self._registry_provider(model_row["provider_id"])
            provider_row = self._provider_row(account_id, model_row["provider_id"])
            if not provider_row or not provider_row["is_configured"]:
                raise_error(
                    "invalid_structure", "MODEL_NOT_CONFIGURED", "请先配置该模型服务。"
                )
            api_key = self._api_key_from_row(account_id, provider_row)
            if not api_key:
                raise_error(
                    "invalid_structure", "MODEL_NOT_CONFIGURED", "请先配置该模型服务。"
                )
            api_url = provider_row["api_url"] or provider.default_api_url
            kind, type_checks, type_errors, successes, metadata, listed, conflict = detect_model_type(
                provider, api_url=api_url, api_key=api_key, remote_model_id=model_row["remote_model_id"], cancellation_token=cancellation_token)
            if kind == "unknown" and model_row["model_type"] != "unknown":
                kind = model_row["model_type"]
            checks = {"type": type_checks, "thinking_modes": {}, "aggregate": {}, "non_thinking": {}, "thinking": {}}
            errors = {"type": type_errors, "thinking_modes": {}, "non_thinking": {}, "thinking": {}}
            write = {}
            if kind == "generation":
                current_profile = profile_from_row(model_row) if model_row["model_type"] == "generation" else DEFAULT_CAPABILITY_PROFILE
                current_profiles = capability_profiles_from_row(model_row) if model_row["model_type"] == "generation" else profiles_from_profile(current_profile)
                probe_profile, probe_profiles, gen_metadata, declarations = _probe_metadata_baseline(
                    remote_model=listed, metadata_result=metadata,
                    current_profile=current_profile, current_profiles=current_profiles)
                result = provider.probe_capabilities(api_url=api_url, api_key=api_key, remote_model_id=model_row["remote_model_id"],
                    current_profiles=probe_profiles, thinking_modes=probe_profile.thinking_modes,
                    capability_declarations=declarations, cancellation_token=cancellation_token)
                write = {"profile": _profile_with_probed_thinking_modes(probe_profile, result.profiles, result.checks["thinking_modes"]), "profiles": result.profiles}
                checks.update(result.checks)
                errors.update(result.errors)
                if not conflict:
                    metadata = gen_metadata
            elif kind == "embedding":
                caps, output_dimensions, embedding_checks, embedding_errors = probe_embeddings(provider, api_url=api_url, api_key=api_key,
                    remote_model_id=model_row["remote_model_id"], cancellation_token=cancellation_token, successes=successes,
                    dimensions=model_row["embedding_dimensions"], declared_dimensions=listed.embedding_dimensions if listed else ())
                checks["embedding"], errors["embedding"] = embedding_checks, embedding_errors
                max_batch_size = model_row["max_batch_size"]
                if embedding_checks["batch"] == "unsupported":
                    max_batch_size = 1
                elif embedding_checks["batch"] == "supported" and max_batch_size == 1:
                    max_batch_size = None
                write = {"embedding_capabilities": caps,
                    "embedding_dimensions": output_dimensions if output_dimensions is not None else model_row["embedding_dimensions"],
                    "max_input_tokens": model_row["max_input_tokens"], "max_batch_size": max_batch_size}
            cancellation_token.raise_if_cancelled()
            with self.repository.transaction(account_id, write=True) as connection:
                current_row = connection.get_model(model_id=model_id)
                current_provider = connection.get_provider(provider_id=model_row["provider_id"])
                if not current_row or dict(current_row) != dict(model_row) or dict(current_provider) != dict(provider_row):
                    raise OperationCancelledError("模型配置已经改变。")
                cancellation_token.raise_if_cancelled()
                connection.write_typed_model(model_id=model_id, model_type=kind, model_name=current_row["model_name"], updated_at=now_iso(), **write)
                import json
                connection.connection.execute("UPDATE models SET capability_detection = ? WHERE model_id = ?", (json.dumps({"checks": checks, "errors": errors, "metadata": metadata}, ensure_ascii=False), model_id))
                updated_row = connection.get_model(model_id=model_id)
                cleared = self._reconcile_defaults(connection, updated_row)
            return {"model": model_response(updated_row), "metadata": metadata, "checks": checks, "errors": errors, "cleared_defaults": cleared}
        except OperationCancelledError:
            raise_error(
                "conflict", "MODEL_CAPABILITY_PROBE_CANCELLED", "模型能力识别已停止。"
            )
        except ProviderChatCompletionError as exc:
            raise_provider_error(exc)
        finally:
            self.probes.finish(account_id, model_id, cancellation_token)

    def list_model_defaults(self, account_id: str):
        return self._model_defaults_response(account_id)

    def update_model_defaults(
        self, account_id: str, payload: ModelDefaultsPatchRequest
    ):
        updates = {
            purpose: getattr(payload, purpose)
            for purpose in MODEL_DEFAULT_PURPOSES
            if purpose in payload.model_fields_set
        }
        with self.repository.transaction(account_id, write=True) as connection:
            for purpose, model_id in updates.items():
                if model_id is not None:
                    row = connection.get_model(model_id=model_id)
                    if not row:
                        raise_error(
                            "missing", "MODEL_NOT_FOUND", "模型不存在或未添加。"
                        )
                    if not eligible_for_default(model_response(row), purpose):
                        raise_error("invalid_structure", "INVALID_DEFAULT_MODEL", "模型类型或输入能力不符合此默认用途。")
            for purpose, model_id in updates.items():
                self._set_model_default_in_connection(connection, purpose, model_id)
        return self._model_defaults_response(account_id)

    def delete_model(self, account_id: str, model_id: str):
        with self.repository.transaction(account_id, write=True) as connection:
            row = connection.get_model(model_id=model_id)
            if not row:
                raise_error("missing", "MODEL_NOT_FOUND", "模型不存在或未添加。")
            self.probes.cancel(account_id, model_id)
            connection.delete_model(model_id=model_id)
        self.probes.cancel(account_id, model_id)
        return {"model_id": model_id, "deleted": True}
