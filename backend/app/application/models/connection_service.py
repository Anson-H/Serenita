"""First-use state and official connections owned by one local account."""
import json
from datetime import timedelta
from urllib.parse import urlsplit

from backend.app.core.errors import raise_error, SerenitaError
from backend.app.core.time import local_now, local_now_iso, parse_local_datetime
from backend.app.domain.model_capabilities import MODEL_DEFAULT_PURPOSES, aggregate_capability_profile, capability_profiles_from_mapping, eligible_for_default
from backend.app.providers.serenita import SerenitaProvider, official_http
from backend.app.providers.errors import ProviderChatCompletionError
from backend.app.repositories.models.provider_repository import ModelProviderRepository
from backend.app.repositories.models.connection_repository import ModelConnectionRepository
from backend.app.repositories.auth_repository import AuthRepository
from backend.app.storage.crypto import seal_secret, unseal_secret
from backend.app.storage.models.codec import model_response
from backend.app.storage.paths import app_paths


class ModelConnectionService:
    def __init__(self, *, paths=None, official_service=None):
        self.paths = paths or app_paths()
        self.models = ModelProviderRepository(paths=self.paths)
        self.official_service = official_service

    def repository(self, account_id):
        return ModelConnectionRepository(paths=self.paths, account_id=account_id)

    def provider(self, account_id):
        return SerenitaProvider(account_id=account_id, paths=self.paths, official_service=self.official_service)

    def status(self, account_id):
        """Read live connection, onboarding and default-model readiness for one account."""
        provider = self.provider(account_id)
        connected = provider.connection_row()["is_configured"]
        catalog = self.current_catalog(account_id) if connected else {"models": [], "service_status": "disconnected"}
        connected = connected and catalog.get("service_status") != "disconnected"
        repository = self.repository(account_id)
        state = repository.expire_device()
        account_name = state["official_account_name"]
        if provider.config.official:
            account = AuthRepository(paths=self.paths).account_by_id(account_id)
            account_name = account["account_name"] if account else None
        readiness = {}
        with self.models.transaction(account_id) as transaction:
            rows = {purpose: transaction.default_model(purpose) for purpose in MODEL_DEFAULT_PURPOSES}
        for purpose, row in rows.items():
            ready = bool(row and eligible_for_default(model_with_service_status(model_response(row), catalog), purpose)
                and self._provider_configured(account_id, row["provider_id"]))
            readiness[purpose] = {"ready": ready, "model_id": row["model_id"] if row else None,
                "reason": None if ready else "请配置此用途的可用模型。"}
        return {"deployment_mode": "official" if provider.config.official else "self_hosted",
            "api_url": provider.config.official_url,
            "service_available": provider.config.official or bool(provider.config.official_url),
            "connected": connected, "connection_error": catalog.get("error"),
            "account_name": account_name, "expires_at": state["expires_at"],
            "onboarding_status": state["onboarding_status"],
            "needs_onboarding": not provider.config.official and state["onboarding_status"] == "pending" and not any(value["ready"] for value in readiness.values()),
            "readiness": readiness, **self._device_view(state)}

    def _provider_configured(self, account_id, provider_id):
        """Read connection readiness without depending on the settings service."""
        from backend.app.application.models.provider_resolution import resolve_provider, configured_provider_row
        provider = resolve_provider(provider_id, account_id=account_id, repository=self.models,
                                    paths=self.paths, official_service=self.official_service)
        if provider_id == "serenita":
            return provider.connection_row()["is_configured"]
        row = configured_provider_row(provider, self.models.get_provider(account_id, provider_id))
        return bool(row and row["is_configured"])

    @staticmethod
    def _device_view(state):
        return {key: state[key] for key in ("user_code", "verification_uri", "device_expires_at", "next_poll_at")}

    def start(self, account_id):
        """Reuse a live grant or request one device code under an account operation claim."""
        provider = self.provider(account_id)
        if provider.config.official:
            self.sync_catalog(account_id, initialize_defaults=True)
            self.repository(account_id).update_local(onboarding_status="completed")
            return self.status(account_id)
        if not provider.config.official_url:
            raise_error("missing", "OFFICIAL_URL_MISSING", "部署管理员尚未配置官方模型服务地址。")
        repository = self.repository(account_id)
        with repository.authorization_operation("start") as claim:
            state = claim.state
            connected = bool(state["encrypted_token"] and state["expires_at"] and parse_local_datetime(state["expires_at"]) > local_now() and state["official_url"] == provider.config.official_url)
            pending = bool(state["encrypted_device_code"] and state["device_expires_at"] and parse_local_datetime(state["device_expires_at"]) > local_now() and state["official_url"] == provider.config.official_url)
            if not connected and not pending:
                value = official_http(provider.config.official_url, "/api/serenita/device/authorize", payload={"client_id": "serenita-self-hosted", "client_name": "Serenita 自部署"})
                target = urlsplit(provider.config.official_url)
                if any((urlsplit(value[key]).scheme, urlsplit(value[key]).netloc) != (target.scheme, target.netloc)
                       for key in ("verification_uri", "verification_uri_complete")):
                    raise_error("invalid_structure", "INVALID_AUTHORIZATION_URL", "官方授权地址与部署配置不一致。")
                interval = max(5, value["interval"])
                accepted = repository.commit_authorization(claim, official_url=provider.config.official_url,
                    encrypted_device_code=seal_secret(account_id, "serenita-device", value["device_code"], paths=self.paths),
                    user_code=value["user_code"], verification_uri=value["verification_uri_complete"],
                    device_expires_at=value["expires_at"], poll_interval=interval,
                    next_poll_at=(local_now() + timedelta(seconds=interval)).isoformat())
                if not accepted:
                    self._discard_remote_device(provider, value["device_code"])
        return self.status(account_id)

    def cancel(self, account_id, user_code):
        """Cancel the matching device request; preserve approval that won remotely."""
        provider, repository = self.provider(account_id), self.repository(account_id)
        with repository.authorization_operation("cancel") as claim:
            state = claim.state
            if state["user_code"] != user_code or not state["encrypted_device_code"]:
                result = "superseded"
            elif state["device_expires_at"] and parse_local_datetime(state["device_expires_at"]) <= local_now():
                repository.commit_authorization(claim, clear_device=True)
                result = "expired_token"
            elif state["official_url"] != provider.config.official_url:
                repository.commit_authorization(claim, clear_device=True)
                result = "access_denied"
            else:
                code = unseal_secret(account_id, "serenita-device", state["encrypted_device_code"], paths=self.paths)
                value = official_http(provider.config.official_url, "/api/serenita/device/cancel", payload={"client_id": "serenita-self-hosted", "device_code": code})
                if value["status"] in {"approved", "consumed"}:
                    result = "approved" if repository.commit_authorization(claim) else "superseded"
                else:
                    result = "access_denied" if repository.commit_authorization(claim, clear_device=True) else "superseded"
        # Approval may win the remote decision. Complete it after releasing the claim.
        if result == "approved":
            value = self.poll(account_id, user_code)
            if value.get("user_code") == user_code:
                value["authorization_status"] = "approved"
            return value
        return {**self.status(account_id), "authorization_status": result}

    def poll(self, account_id, user_code):
        """Exchange a due device request and conditionally commit its authorized grant."""
        provider, repository = self.provider(account_id), self.repository(account_id)
        authorization_error, exchanged = None, False
        with repository.authorization_operation("poll") as claim:
            state = claim.state
            if state["user_code"] != user_code:
                result = "superseded"
            elif not state["encrypted_device_code"]:
                result = "disconnected"
            elif state["official_url"] != provider.config.official_url:
                raise_error("conflict", "OFFICIAL_URL_CHANGED", "官方服务地址已改变，请重新连接。")
            elif parse_local_datetime(state["device_expires_at"]) <= local_now():
                repository.commit_authorization(claim, clear_device=True)
                result = "expired_token"
            elif state["next_poll_at"] and parse_local_datetime(state["next_poll_at"]) > local_now():
                result = "authorization_pending"
            else:
                code = unseal_secret(account_id, "serenita-device", state["encrypted_device_code"], paths=self.paths)
                try:
                    value = official_http(provider.config.official_url, "/api/serenita/device/token", payload={"device_code": code,
                        "client_id": "serenita-self-hosted", "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
                except ProviderChatCompletionError as error:
                    authorization_error = str(error)
                    value = {"error": "authorization_pending", "interval": state["poll_interval"] * 2}
                result = value.get("error", "connected")
                if result == "connected":
                    exchanged = repository.commit_authorization(claim, clear_device=True,
                        official_account_id=value["account_id"], official_account_name=value["account_name"],
                        connection_id=value["connection_id"], encrypted_token=seal_secret(account_id, "serenita-token", value["access_token"], paths=self.paths),
                        expires_at=value["expires_at"], onboarding_status="pending")
                    if not exchanged:
                        self._revoke_remote(provider, value["access_token"])
                        result = "superseded"
                elif result in {"authorization_pending", "slow_down"}:
                    interval = max(state["poll_interval"], value.get("interval", 5))
                    next_poll = min(local_now() + timedelta(seconds=interval), parse_local_datetime(state["device_expires_at"]))
                    if not repository.commit_authorization(claim, poll_interval=interval, next_poll_at=next_poll.isoformat()):
                        result = "superseded"
                elif result in {"expired_token", "access_denied", "invalid_grant"}:
                    if not repository.commit_authorization(claim, clear_device=True):
                        result = "superseded"
        if exchanged:
            try:
                self.sync_catalog(account_id, initialize_defaults=True)
            except (ProviderChatCompletionError, SerenitaError) as error:
                authorization_error = str(error)
        return {**self.status(account_id), "authorization_status": result, "authorization_error": authorization_error}

    @staticmethod
    def _revoke_remote(provider, token):
        try:
            official_http(provider.config.official_url, "/api/serenita/session", token=token, method="DELETE")
            return True
        except ProviderChatCompletionError as error:
            return error.code == "OFFICIAL_LOGIN_REQUIRED"

    def _discard_remote_device(self, provider, code):
        """Resolve and revoke approval that raced local disconnection."""
        try:
            value = official_http(provider.config.official_url, "/api/serenita/device/cancel", payload={"client_id": "serenita-self-hosted", "device_code": code})
            if value["status"] in {"approved", "consumed"}:
                grant = official_http(provider.config.official_url, "/api/serenita/device/token", payload={"device_code": code,
                    "client_id": "serenita-self-hosted", "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
                return "access_token" in grant and self._revoke_remote(provider, grant["access_token"])
            return value["status"] in {"denied", "expired"}
        except ProviderChatCompletionError:
            return False

    def disconnect(self, account_id):
        """Invalidate local authorization immediately, then revoke remote access."""
        provider = self.provider(account_id)
        state = self.repository(account_id).disconnect_local(delete_models=not provider.config.official)
        revoked = provider.config.official
        if not provider.config.official and state["official_url"] == provider.config.official_url:
            if state["encrypted_token"]:
                token = unseal_secret(account_id, "serenita-token", state["encrypted_token"], paths=self.paths)
                revoked = self._revoke_remote(provider, token)
            elif state["encrypted_device_code"]:
                code = unseal_secret(account_id, "serenita-device", state["encrypted_device_code"], paths=self.paths)
                revoked = self._discard_remote_device(provider, code)
        return {"disconnected": True, "remote_revoked": revoked}

    def choose(self, account_id, choice):
        if choice == "serenita":
            return self.start(account_id)
        self.repository(account_id).update_local(onboarding_status="skipped" if choice == "later" else "completed")
        return self.status(account_id)

    def current_catalog(self, account_id):
        provider = self.provider(account_id)
        if not provider.connection_row()["is_configured"]:
            return {"models": [], "service_status": "disconnected"}
        state = self.repository(account_id).local_state()
        try:
            initialize = state["onboarding_status"] == "pending"
            return self.sync_catalog(account_id, initialize_defaults=initialize)
        except (ProviderChatCompletionError, SerenitaError) as error:
            if isinstance(error, SerenitaError) and error.kind not in {"unauthenticated", "upstream_failure"}:
                raise
            code = getattr(error, "code", None) or (error.detail.get("code") if isinstance(error, SerenitaError) else None)
            status = "disconnected" if code in {"OFFICIAL_LOGIN_REQUIRED", "OFFICIAL_ACCOUNT_UNAVAILABLE"} else "unreachable"
            if status == "disconnected" and not provider.config.official:
                with self.repository(account_id).catalog_transaction() as connection:
                    current = connection.state()
                    if current["encrypted_token"] == state["encrypted_token"]:
                        connection.clear_grant()
            return {"models": [], "service_status": status, "error": str(error)}

    def sync_catalog(self, account_id, *, remote_model_id=None, cancellation_token=None, initialize_defaults=False):
        provider = self.provider(account_id)
        state = self.repository(account_id).local_state()
        catalog = provider.catalog(cancellation_token)
        selected = [item for item in catalog["models"] if remote_model_id is None or item["remote_model_id"] == remote_model_id]
        if remote_model_id and not selected:
            raise_error("missing", "OFFICIAL_MODEL_UNAVAILABLE", "此模型未开放或已下线。")
        now = local_now_iso()
        with self.repository(account_id).catalog_transaction() as connection:
            current = connection.state()
            if not provider.config.official and (not current["encrypted_token"] or current["encrypted_token"] != state["encrypted_token"]):
                raise_error("unauthenticated", "OFFICIAL_LOGIN_REQUIRED", "授权已改变，请重新读取连接状态。")
            transaction = connection.models
            existing = {row["model_id"] for row in transaction.list_models() if row["provider_id"] == "serenita"}
            chosen = set(existing)
            if remote_model_id:
                chosen.update(item["model_id"] for item in selected)
            if initialize_defaults and not provider.config.official:
                chosen.update(item["model_id"] for item in selected)
            if initialize_defaults:
                for purpose in MODEL_DEFAULT_PURPOSES:
                    if not transaction.default_model(purpose):
                        model = next((item for item in selected if eligible_for_default(item, purpose)), None)
                        if model:
                            chosen.add(model["model_id"])
            selected = [item for item in selected if item["model_id"] in chosen]
            if selected:
                transaction.save_provider(provider_id="serenita", provider_name="Serenita", api_url=provider.default_api_url,
                    official_url=provider.default_official_url, encrypted_api_key=None, created_at=now, updated_at=now)
            for item in selected:
                previous = transaction.get_model(model_id=item["model_id"])
                previous_report = json.loads(previous["capability_detection"]) if previous and previous["capability_detection"] else {}
                if previous and previous_report.get("catalog_revision") == item["catalog_revision"]:
                    continue
                if previous and previous["model_type"] == "embedding" and item["model_type"] == "embedding" and previous["embedding_dimensions"] is not None and previous["embedding_dimensions"] != item["embedding_dimensions"]:
                    raise_error("conflict", "VECTOR_MODEL_IMMUTABLE", "官方向量模型身份发生变化，请联系服务管理员。")
                transaction.save_model(model_id=item["model_id"], provider_id="serenita", remote_model_id=item["remote_model_id"],
                    model_name=item["model_name"], created_at=now, updated_at=now)
                profiles = capability_profiles_from_mapping(item["capability_profiles"]) if item["model_type"] == "generation" else None
                profile = aggregate_capability_profile(profiles, thinking_modes=item["thinking_modes"],
                    context_window_tokens=item["context_window_tokens"], max_output_tokens=item["max_output_tokens"]) if profiles else None
                transaction.write_typed_model(model_id=item["model_id"], model_type=item["model_type"], model_name=item["model_name"],
                    profile=profile, profiles=profiles, embedding_capabilities=item["embedding_capabilities"],
                    embedding_dimensions=item["embedding_dimensions"], max_input_tokens=item["max_input_tokens"], max_batch_size=item["max_batch_size"], updated_at=now)
                report = item["capability_detection"] or {"metadata": {"status": "refreshed", "message": "已同步服务端模型参数。"},
                    "checks": {"thinking_modes": {}, "aggregate": {}, "non_thinking": {}, "thinking": {}},
                    "errors": {"thinking_modes": {}, "non_thinking": {}, "thinking": {}}}
                report = {**report, "catalog_revision": item["catalog_revision"]}
                transaction.save_capability_detection(item["model_id"], report)
            if remote_model_id or initialize_defaults:
                for purpose in MODEL_DEFAULT_PURPOSES:
                    if transaction.default_model(purpose):
                        continue
                    model = next((item for item in selected if eligible_for_default(item, purpose)), None)
                    row = transaction.get_model(model_id=model["model_id"]) if model else None
                    if row and eligible_for_default(model_response(row), purpose):
                        transaction.set_default(purpose, model_id=row["model_id"])
            if initialize_defaults:
                connection.complete_onboarding()
        return catalog


def model_with_service_status(model, catalog):
    if model is None or model["provider_id"] != "serenita":
        return model
    status = catalog["service_status"]
    if status == "available":
        published = next((item for item in catalog["models"] if item["model_id"] == model["model_id"]), None)
        status = published["service_status"] if published else "offline"
    return {**model, "service_status": status}
