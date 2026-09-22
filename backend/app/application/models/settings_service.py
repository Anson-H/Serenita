from backend.app.application.models.inspection import inspect_model, remote_model_payload
from backend.app.application.models.provider_connection import test_provider_connection
from backend.app.core.runtime.model_probe_tasks import probes_for_paths
from backend.app.storage.paths import app_paths
from backend.app.application.models.provider_errors import raise_provider_error
from typing import Any
from backend.app.core.cancellation import CancellationToken, OperationCancelledError
from backend.app.core.errors import raise_error
from backend.app.core.time import local_now_iso
from backend.app.domain.model_capabilities import (
    EmbeddingCapabilities,
    eligible_for_default,
    DEFAULT_CAPABILITY_PROFILE,
    MODEL_DEFAULT_PURPOSES,
    ModelCapabilityProfiles,
    ModelCapabilityProfile,
    capability_profiles_from_mapping,
    capability_response,
    profiles_from_profile,
)
from backend.app.storage.models.codec import (
    capability_profiles_from_row,
    profile_from_row,
)
from backend.app.providers.base import ModelProvider
from backend.app.providers.errors import (
    ProviderChatCompletionError,
    ProviderModelListError,
)
from backend.app.providers.default_registry import create_default_provider_registry
from backend.app.storage.models.provider_secrets import (
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
from backend.app.storage.models.codec import model_response
from backend.app.repositories.models.provider_repository import ModelProviderRepository
from backend.app.application.models.provider_resolution import resolve_provider, configured_provider_row, validate_provider_url, provider_metadata

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
    def __init__(self, repository=None, provider_registry=None, *, paths=None, official_service=None):
        self.paths = paths or getattr(repository, "paths", None) or app_paths()
        self.repository = repository or ModelProviderRepository(paths=self.paths)
        self.probes = probes_for_paths(self.paths)
        self.provider_registry = provider_registry
        self.official_service = official_service

    def _registry_provider(self, provider_id: str, account_id=None, *, transaction=None) -> ModelProvider:
        return resolve_provider(provider_id, account_id=account_id, repository=self.repository,
            registry=self.provider_registry or create_default_provider_registry(), paths=self.paths,
            official_service=self.official_service,
            transaction=transaction)

    def _provider_row(self, account_id: str, provider_id: str):
        provider = self._registry_provider(provider_id, account_id)
        if provider_id == "serenita":
            return provider.connection_row()
        with self.repository.transaction(account_id) as connection:
            return configured_provider_row(provider, connection.get_provider(provider_id=provider_id))


    def _provider_summary(
        self, account_id: str, provider: ModelProvider
    ) -> dict[str, Any]:
        if provider.provider_id == "serenita":
            return provider.public_summary()
        row = self._provider_row(account_id, provider.provider_id)
        return {
            **provider_metadata(provider),
            "api_url": row["api_url"] if row else provider.default_api_url,
            "official_url": row["official_url"]
            if row and row["official_url"] is not None
            else provider.default_official_url,
            "has_api_key": bool(row["encrypted_api_key"]) if row else False,
            "is_configured": bool(row["is_configured"]) if row else False,
        }

    def _api_key_from_row(self, account_id: str, row) -> str:
        return provider_secret_from_row(account_id, row, paths=self.paths)

    def _saved_api_key(self, account_id: str, provider_id: str) -> str:
        return self._api_key_from_row(
            account_id, self._provider_row(account_id, provider_id)
        )



    def _model_defaults_response(self, account_id: str) -> dict[str, Any]:
        with self.repository.transaction(account_id) as connection:
            defaults = {}
            for purpose in MODEL_DEFAULT_PURPOSES:
                row = connection.default_model(purpose)
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
            updated_at=local_now_iso(),
            profile=profile,
            profiles=profiles,
            model_id=row["model_id"],
        )
        return connection.get_model(model_id=row["model_id"])

    def list_model_providers(self, account_id: str):
        registry = self.provider_registry or create_default_provider_registry()
        with self.repository.transaction(account_id) as connection:
            custom_ids = [row["provider_id"] for row in connection.list_providers() if row["provider_id"].startswith("custom_")]
        custom = [self._registry_provider(identifier, account_id) for identifier in custom_ids]
        return {
            "providers": [
                self._provider_summary(account_id, provider)
                for provider in (self._registry_provider("serenita", account_id), *registry.providers(), *custom)
            ]
        }

    def reveal_model_provider_credential(self, account_id: str, provider_id: str):
        self._require_user_provider(provider_id)
        provider = self._registry_provider(provider_id, account_id)
        api_key = self._saved_api_key(account_id, provider.provider_id)
        if not api_key:
            raise_error(
                "missing", "MODEL_NOT_CONFIGURED", "该模型服务尚未配置 API key。"
            )
        return {"provider_id": provider.provider_id, "api_key": api_key}

    def create_model_provider(self, account_id: str, payload: ModelProviderSaveRequest):
        if payload.provider_id is None:
            from uuid import uuid4
            from backend.app.providers.compatible import CompatibleProvider
            provider = CompatibleProvider("custom_" + uuid4().hex,
                self._validate_provider_name(account_id, payload.provider_name),
                validate_provider_url(payload.api_url))
        else:
            self._require_user_provider(payload.provider_id)
            provider = self._registry_provider(payload.provider_id, account_id)
        existing = self.repository.get_provider(account_id, provider.provider_id)
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
        timestamp = local_now_iso()
        with self.repository.transaction(account_id, write=True) as connection:
            if provider.provider_kind == "custom":
                self._validate_provider_name(account_id, provider.provider_name, provider_id=provider.provider_id, transaction=connection)
            connection.save_provider(
                provider_id=provider.provider_id,
                provider_name=provider.provider_name,
                api_url=validate_provider_url(api_url or provider.default_api_url),
                official_url=validate_provider_url(official_url, optional=True),
                encrypted_api_key=sealed_key,
                created_at=timestamp,
                updated_at=timestamp,
            )
        return self._provider_summary(account_id, provider)

    def update_model_provider(
        self, account_id: str, provider_id: str, payload: ModelProviderPatchRequest
    ):
        self._require_user_provider(provider_id)
        provider = self._registry_provider(provider_id, account_id)
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
        timestamp = local_now_iso()
        with self.repository.transaction(account_id, write=True) as connection:
            if payload.provider_name is not None:
                if provider.provider_kind != "custom":
                    raise_error("invalid_structure", "PROVIDER_NAME_READ_ONLY", "内置提供方名称不可修改。")
                name = self._validate_provider_name(account_id, payload.provider_name, provider_id=provider_id, transaction=connection)
                connection.rename_provider(provider_id=provider_id, provider_name=name)
                provider.provider_name = name
            connection.update_provider(
                api_url=validate_provider_url(next_api_url or provider.default_api_url),
                official_url=validate_provider_url(next_official_url, optional=True),
                encrypted_api_key=next_sealed_key,
                updated_at=timestamp,
                provider_id=provider_id,
            )
        return self._provider_summary(account_id, provider)

    @staticmethod
    def _require_user_provider(provider_id):
        if provider_id == "serenita":
            raise_error("forbidden", "MANAGED_PROVIDER_READ_ONLY", "Serenita 官方连接由官方账号管理。")

    def _validate_provider_name(self, account_id, name, *, provider_id=None, transaction=None):
        name = (name or "").strip()
        if not name or len(name) > 50:
            raise_error("invalid_structure", "INVALID_PROVIDER_NAME", "提供方名称应为 1 至 50 个字符。")
        registry = self.provider_registry or create_default_provider_registry()
        reserved = {"serenita", *(provider.provider_name.casefold() for provider in registry.providers())}
        if transaction is None:
            with self.repository.transaction(account_id) as connection:
                rows = connection.list_providers()
        else:
            rows = transaction.list_providers()
        names = {row["provider_name"].casefold() for row in rows if row["provider_id"] != provider_id}
        if name.casefold() in reserved | names:
            raise_error("conflict", "PROVIDER_NAME_EXISTS", "提供方名称已存在或为内置名称。")
        return name

    def delete_model_provider(self, account_id, provider_id):
        provider = self._registry_provider(provider_id, account_id)
        if provider.provider_kind != "custom":
            raise_error("forbidden", "PROVIDER_DELETE_FORBIDDEN", "仅支持删除自定义提供方。")
        with self.repository.transaction(account_id, write=True) as connection:
            model_ids = [row["model_id"] for row in connection.list_models() if row["provider_id"] == provider_id]
            for model_id in model_ids:
                self.probes.cancel(account_id, model_id)
            connection.delete_provider(provider_id)
        return {"provider_id": provider_id, "deleted": True, "deleted_model_ids": model_ids}

    def test_model_provider(
        self, account_id: str, provider_id: str, payload: ModelProviderTestRequest,
        *, cancellation_token=None,
    ):
        provider = self._registry_provider(provider_id, account_id)
        if provider_id == "serenita":
            return provider.test_access(cancellation_token=cancellation_token)
        api_key = (payload.api_key or "").strip() or self._saved_api_key(
            account_id, provider_id
        )
        if not api_key and provider.requires_api_key:
            raise_error(
                "invalid_structure", "MODEL_NOT_CONFIGURED", "请先输入或保存 API key。"
            )
        saved_provider = self._provider_row(account_id, provider_id)
        test_arguments = dict(
            api_url=payload.api_url
            or (saved_provider["api_url"] if saved_provider else None)
            or provider.default_api_url,
            api_key=api_key,
            **({"cancellation_token": cancellation_token} if cancellation_token is not None else {}),
        )
        return test_provider_connection(provider, **test_arguments)

    def list_remote_models(self, account_id: str, provider_id: str, *, cancellation_token=None):
        provider = self._registry_provider(provider_id, account_id)
        if provider_id == "serenita":
            return provider.catalog(cancellation_token=cancellation_token)
        row = self._provider_row(account_id, provider_id)
        if not row or not row["is_configured"]:
            raise_error(
                "invalid_structure", "MODEL_NOT_CONFIGURED", "请先配置该模型服务。"
            )
        api_key = self._saved_api_key(account_id, provider_id)
        if not api_key and provider.requires_api_key:
            raise_error(
                "invalid_structure", "MODEL_NOT_CONFIGURED", "请先输入或保存 API key。"
            )
        try:
            remote_models = provider.list_models(
                api_url=row["api_url"] or provider.default_api_url, api_key=api_key,
                **({"cancellation_token": cancellation_token} if cancellation_token is not None else {}),
            )
        except ProviderModelListError as exc:
            raise_provider_error(exc)
        return {
            "provider_id": provider.provider_id,
            "models": [
                remote_model_payload(model) for model in remote_models
            ],
        }

    def add_model(
        self,
        account_id: str,
        payload: AddModelRequest,
        cancellation_token: CancellationToken | None = None,
    ):
        provider = self._registry_provider(payload.provider_id, account_id)
        if payload.provider_id == "serenita":
            from backend.app.application.models.connection_service import ModelConnectionService
            catalog = ModelConnectionService(paths=self.paths, official_service=self.official_service).sync_catalog(account_id, remote_model_id=payload.remote_model_id, cancellation_token=cancellation_token)
            from backend.app.application.models.connection_service import model_with_service_status
            return model_with_service_status(model_response(self.repository.get_model(account_id, f"serenita:{payload.remote_model_id}")), catalog)
        provider_row = self._provider_row(account_id, payload.provider_id)
        if not provider_row or not provider_row["is_configured"]:
            raise_error(
                "invalid_structure", "MODEL_NOT_CONFIGURED", "请先配置该模型服务。"
            )
        if not payload.remote_model_id.strip():
            raise_error("invalid_structure", "INVALID_MODEL_ID", "模型 ID 不能为空。")
        model_id = f"{payload.provider_id}:{payload.remote_model_id}"
        model_name = payload.remote_model_id
        timestamp = local_now_iso()
        model_type = payload.model_type
        with self.repository.transaction(account_id, write=True) as connection:
            existing = connection.get_model(model_id=model_id)
            connection.save_model(
                model_id=model_id,
                provider_id=payload.provider_id,
                remote_model_id=payload.remote_model_id,
                model_name=model_name,
                created_at=timestamp,
                updated_at=timestamp,
            )
            # Save catalog types immediately. Interface-based type detection and
            # capability checks run in the separate model inspection request.
            if model_type in {"generation", "embedding"} and (
                existing is None or existing["model_type"] == "unknown"
            ):
                if model_type == "generation":
                    profile = DEFAULT_CAPABILITY_PROFILE
                    connection.write_typed_model(
                        model_id=model_id,
                        model_type="generation",
                        model_name=model_name,
                        profile=profile,
                        profiles=profiles_from_profile(profile),
                        updated_at=timestamp,
                    )
                else:
                    protocols = provider.embedding_protocols(
                        provider_row["api_url"] or provider.default_api_url
                    )
                    embedding_capabilities = EmbeddingCapabilities(
                        supports_text=True,
                        independent="unverified",
                        fusion="unverified",
                        protocol=protocols[0] if protocols else "compatible",
                    ).model_dump()
                    connection.write_typed_model(
                        model_id=model_id,
                        model_type="embedding",
                        model_name=model_name,
                        embedding_capabilities=embedding_capabilities,
                        updated_at=timestamp,
                    )
            row = connection.get_model(model_id=model_id)
        return model_response(row)

    def list_models(self, account_id: str):
        with self.repository.transaction(account_id) as connection:
            rows = connection.list_models()
        models = [model_response(row) for row in rows]
        return {"models": models}

    def recommend_missing_defaults(self, account_id):
        models = self.list_models(account_id)["models"]
        configured = {item["provider_id"] for item in self.list_model_providers(account_id)["providers"] if item["is_configured"]}
        with self.repository.transaction(account_id, write=True) as connection:
            for purpose in MODEL_DEFAULT_PURPOSES:
                if connection.default_model(purpose):
                    continue
                candidate = next((item for item in models if item["provider_id"] in configured and eligible_for_default(item, purpose)), None)
                if candidate:
                    connection.set_default(purpose, model_id=candidate["model_id"])
        return self._model_defaults_response(account_id)

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
                    **{key: getattr(payload, key) if key in supplied else row[key] for key in ("embedding_dimensions", "max_input_tokens", "max_batch_size")}, updated_at=local_now_iso())
                updated_row = connection.get_model(model_id=model_id)
                cleared = self._reconcile_defaults(connection, updated_row, auto_chat=False)
                return {**model_response(updated_row), "cleared_defaults": cleared}
            if any(getattr(payload, key) is not None for key in supplied & {"embedding_capabilities", "embedding_dimensions", "max_input_tokens", "max_batch_size"}):
                raise_error("invalid_structure", "INVALID_MODEL_CAPABILITY", "生成模型不使用向量参数。")
            if row["model_type"] != "generation":
                initial_profile = ModelCapabilityProfile(thinking_modes=payload.thinking_modes or ["default"])
                connection.write_typed_model(model_id=model_id, model_type="generation", model_name=row["model_name"], profile=initial_profile, profiles=profiles_from_profile(initial_profile), updated_at=local_now_iso())
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
                provider = self._registry_provider(row["provider_id"], account_id, transaction=connection)
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
                if (
                    "capability_profiles" not in supplied
                    and current_profiles.thinking.availability == "unavailable"
                    and any(mode not in {"default", "off"} for mode in thinking_modes)
                ):
                    profiles = profiles_from_profile(
                        ModelCapabilityProfile(
                            supports_text=current.supports_text,
                            file_mime_types=list(current.file_mime_types),
                            thinking_modes=thinking_modes,
                            supports_tool_calling=current.supports_tool_calling,
                            default_thinking_state=current.default_thinking_state,
                            context_window_tokens=current.context_window_tokens,
                            max_output_tokens=current.max_output_tokens,
                        )
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
                supports_text=current.supports_text,
                file_mime_types=list(current.file_mime_types),
                thinking_modes=thinking_modes,
                supports_tool_calling=current.supports_tool_calling,
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
            provider = self._registry_provider(model_row["provider_id"], account_id)
            provider_row = self._provider_row(account_id, model_row["provider_id"])
            if not provider_row or not provider_row["is_configured"]:
                raise_error(
                    "invalid_structure", "MODEL_NOT_CONFIGURED", "请先配置该模型服务。"
                )
            api_key = self._api_key_from_row(account_id, provider_row)
            if not api_key and provider.requires_api_key:
                raise_error(
                    "invalid_structure", "MODEL_NOT_CONFIGURED", "请先配置该模型服务。"
                )
            api_url = provider_row["api_url"] or provider.default_api_url
            if model_row["provider_id"] == "serenita":
                catalog = provider.catalog(cancellation_token)
                provider.inspection_model = next((item for item in catalog["models"] if item["remote_model_id"] == model_row["remote_model_id"]), None)
                if provider.inspection_model is None:
                    raise_error("missing", "OFFICIAL_MODEL_UNAVAILABLE", "此模型未开放或已下线。")
            inspection = inspect_model(provider, model_response(model_row),
                api_url=api_url, api_key=api_key, cancellation_token=cancellation_token)
            kind, write = inspection.model_type, inspection.parameters
            metadata, checks, errors = inspection.metadata, inspection.checks, inspection.errors
            cancellation_token.raise_if_cancelled()
            with self.repository.transaction(account_id, write=True) as connection:
                current_row = connection.get_model(model_id=model_id)
                current_provider = provider.connection_row() if model_row["provider_id"] == "serenita" else configured_provider_row(provider, connection.get_provider(provider_id=model_row["provider_id"]))
                if not current_row or dict(current_row) != dict(model_row) or current_provider != dict(provider_row):
                    raise OperationCancelledError("模型配置已经改变。")
                cancellation_token.raise_if_cancelled()
                connection.write_typed_model(model_id=model_id, model_type=kind, model_name=current_row["model_name"], updated_at=local_now_iso(), **write)
                import json
                report = {"checks": checks, "errors": errors, "metadata": metadata}
                previous_report = json.loads(current_row["capability_detection"]) if current_row["capability_detection"] else {}
                if "catalog_revision" in previous_report:
                    report["catalog_revision"] = previous_report["catalog_revision"]
                connection.save_capability_detection(model_id, report)
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
        catalog = None
        if any(value and value.startswith("serenita:") for value in updates.values()):
            from backend.app.application.models.connection_service import ModelConnectionService
            catalog = ModelConnectionService(paths=self.paths, official_service=self.official_service).current_catalog(account_id)
        with self.repository.transaction(account_id, write=True) as connection:
            for purpose, model_id in updates.items():
                if model_id is not None:
                    row = connection.get_model(model_id=model_id)
                    if not row:
                        raise_error(
                            "missing", "MODEL_NOT_FOUND", "模型不存在或未添加。"
                        )
                    model = model_response(row)
                    if catalog is not None:
                        from backend.app.application.models.connection_service import model_with_service_status
                        model = model_with_service_status(model, catalog)
                    if not eligible_for_default(model, purpose):
                        raise_error("invalid_structure", "INVALID_DEFAULT_MODEL", "模型类型或输入能力不符合此默认用途。")
            for purpose, model_id in updates.items():
                connection.set_default(purpose, model_id=model_id)
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
