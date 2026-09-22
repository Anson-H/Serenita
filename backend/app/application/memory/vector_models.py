"""Fixed embedding parameters, vector spaces and a shared model request budget."""
from __future__ import annotations

from copy import deepcopy
import json
import time
from uuid import uuid5, NAMESPACE_URL

from backend.app.core.values import digest as fingerprint
from backend.app.domain.model_capabilities import supported_embedding_modalities
from backend.app.domain.memory.vectors import canonical_vector, fail
from backend.app.schemas.memory.index import VectorSpaceInput






class MemoryVectorModels:
    def __init__(self, memory, *, embedding=None, cancellation_token=None, deadline=None):
        self.memory, self.models = memory, memory.models
        self.embedding = embedding or self.models.complete_embedding_for_account
        self.cancellation_token, self.deadline = cancellation_token, deadline

    def default_model_id(self, account_id):
        work = self._model_work(account_id)
        key = "model_purpose:text_embedding"
        if work is not None:
            saved = work.get(key)
            if saved is not None:
                model_id = saved["model_id"]
                self.model_snapshot(account_id, model_id)
                return model_id
        model = self.models.default_model_for_account(account_id, "text_embedding")
        if work is not None and model is not None:
            model = self.model_snapshot(account_id, model["model_id"])
            work.put(key, {"model_id": model["model_id"]})
        return model["model_id"] if model else None

    def _model_work(self, account_id):
        from backend.app.repositories.memory.processing.staging_scope import staging
        draft = staging()
        if draft is None or draft.repo is not self.memory.repository or draft.account != account_id:
            return None
        return draft.work

    def model_snapshot(self, account_id, model_id):
        current = self.models.model_for_account(account_id, model_id)
        work = self._model_work(account_id)
        if work is None:
            return current
        if current is None or current.get("model_type") != "embedding":
            fail("MEMORY_EMBEDDING_MODEL_UNAVAILABLE", "指定向量模型当前不可用。")
        key = "model_id:" + model_id
        saved = work.get(key)
        if saved is None:
            saved = deepcopy(current)
            work.put(key, saved)
        return deepcopy(saved)

    def _embedding_endpoint(self, account_id, model, provider):
        api_url = provider["api_url"] or self.models._provider(model["provider_id"]).default_api_url
        work = self._model_work(account_id)
        if work is not None:
            key = "model_endpoint:" + model["model_id"]
            saved = work.get(key)
            if saved is None:
                work.put(key, api_url)
            elif saved != api_url:
                fail("MEMORY_VECTOR_SPACE_CHANGED", "当前服务地址与已固定向量空间不同。")
        return api_url

    def space(self, account_id, member_id, model_id, dimensions=None):
        model = self.model_snapshot(account_id, model_id)
        if model is None or model.get("model_type") != "embedding":
            fail("MEMORY_EMBEDDING_MODEL_UNAVAILABLE", "指定向量模型当前不可用。")
        caps = model.get("embedding_capabilities") or {}
        if caps.get("independent") != "supported" or "text" not in supported_embedding_modalities(caps) or not caps.get("protocol"):
            fail("MEMORY_EMBEDDING_UNVERIFIED", "模型尚未确认支持独立文本向量。")
        dimensions = model.get("embedding_dimensions") if dimensions is None else dimensions
        if type(dimensions) is not int or not 1 <= dimensions <= 65536:
            fail("MEMORY_EMBEDDING_DIMENSIONS_UNKNOWN", "向量空间必须使用已明确的维度。")
        provider = self.models._provider_row(account_id, model["provider_id"])
        if provider is None or not provider["is_configured"]:
            fail("MEMORY_EMBEDDING_MODEL_UNAVAILABLE", "向量模型服务尚未配置。")
        api_url = self._embedding_endpoint(account_id, model, provider)
        # Only behavior-defining public parameters enter the signature. Neither
        # credentials nor provider update timestamps define a vector space.
        signature = fingerprint({"provider_id": model["provider_id"], "api_url": api_url,
            "remote_model_id": model["remote_model_id"], "protocol": caps["protocol"], "mode": "independent",
            "modality": "text", "dimensions": dimensions, "metric": "cosine", "storage": "float32-le"})
        return VectorSpaceInput.model_validate({"space_id": str(uuid5(NAMESPACE_URL, json.dumps(["serenita:vector-space", account_id, member_id, model_id, signature], separators=(",", ":")))),
            "model_id": model_id, "provider_id": model["provider_id"], "remote_model_id": model["remote_model_id"],
            "model_signature": signature, "dimensions": dimensions, "protocol": caps["protocol"]}).model_dump()

    def check_running(self):
        if self.cancellation_token is not None:
            self.cancellation_token.raise_if_cancelled()
        if self.deadline is not None and time.monotonic() >= self.deadline:
            fail("MEMORY_INDEX_TIMEOUT", "本次索引操作的时间预算已用尽。", kind="timeout")

    def embed(self, account_id, member_id, space, text):
        return self.embed_many(account_id, member_id, space, [text])[0]

    def embed_many(self, account_id, member_id, space, texts, *, guard=None):
        """Batch independent inputs and restore their original order, including duplicates."""
        unique = list(dict.fromkeys(texts))
        vectors = {}
        model = self.model_snapshot(account_id, space['model_id'])
        batch_size = min(10, (model or {}).get('max_batch_size') or 10)
        for offset in range(0, len(unique), batch_size):
            batch = unique[offset:offset + batch_size]
            from backend.app.core.model_retry import run_model_request
            from backend.app.application.memory.progress import report_model_retry
            def check_request():
                self.check_running()
                if guard:
                    guard()
            generated = run_model_request(
                lambda: self._request_embeddings(account_id, member_id, space, batch),
                check_running=check_request, on_retry=report_model_retry)
            if guard:
                guard()
            vectors.update(zip(batch, generated))
        return [vectors[text] for text in texts]

    def _request_embeddings(self, account_id, member_id, space, texts):
        self.check_running()
        actual = self.space(account_id, member_id, space["model_id"], space["dimensions"])
        if actual["model_signature"] != space["model_signature"]:
            fail("MEMORY_VECTOR_SPACE_CHANGED", "当前模型配置与绑定空间不同，需要明确的新空间。")
        options = {}
        if self._model_work(account_id) is not None:
            options["model_snapshot"] = self.model_snapshot(account_id, space["model_id"])
        if self.cancellation_token is not None:
            options["cancellation_token"] = self.cancellation_token
        if self.deadline is not None:
            options["timeout_seconds"] = max(.001, self.deadline - time.monotonic())
        result = self.embedding(account_id, space["model_id"], [{"modality": "text", "value": text} for text in texts],
            mode="independent", dimensions=space["dimensions"], **options)
        self.check_running()
        # Check again after the call to detect a concurrent model configuration
        # change. The configured service owns API-key handling.
        after = self.space(account_id, member_id, space["model_id"], space["dimensions"])
        if actual != after or result.model != space["remote_model_id"] or result.mode != "independent" or result.dimensions != space["dimensions"] or len(result.vectors) != len(texts):
            fail("MEMORY_VECTOR_SPACE_CHANGED", "实际向量响应与固定模型空间不一致。")
        return [canonical_vector(vector, space['dimensions'])[0] for vector in result.vectors]

