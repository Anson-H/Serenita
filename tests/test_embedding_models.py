import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.app.agent_runtime.model_types import AssistantModelOutput
from backend.app.application.model_settings_service import ModelSettingsService
from backend.app.core.cancellation import CancellationToken
from backend.app.domain.model_capabilities import EmbeddingCapabilities
from backend.app.providers.base import ModelProvider
from backend.app.providers.aliyun_bailian import AliyunBailianProvider
from backend.app.providers.openrouter import OpenRouterProvider
from backend.app.providers.embeddings import EmbeddingResult, validate_vectors
from backend.app.providers.errors import ProviderChatCompletionError
from backend.app.providers.model_type_probe import detect_model_type, probe_embeddings
from backend.app.providers.registry import ProviderRegistry
from backend.app.providers.types import ProviderModel
from backend.app.schemas.model_provider import AddModelRequest, ModelPatchRequest, ModelDefaultsPatchRequest, ModelProviderSaveRequest


class EmbeddingProvider(ModelProvider):
    provider_id = "embedding_test"
    default_api_url = "https://provider.example/v1"

    def __init__(self):
        super().__init__()
        self.calls = []
        self.generation = False
        self.embedding = True
        self.metadata_type = "unknown"
        self.failure = ProviderChatCompletionError("不存在", upstream_status=404)
        self.started = threading.Event()
        self.release = threading.Event()
        self.block = False

    def embedding_modalities(self, protocol):
        return {"text", "image", "audio", "video", "document"}

    def complete_chat(self, **kwargs):
        self.calls.append("generation")
        if self.generation:
            return AssistantModelOutput(content="OK")
        raise self.failure

    def complete_embedding(self, *, inputs, mode="independent", dimensions=None, cancellation_token=None, **kwargs):
        self.calls.append((inputs[0]["modality"], mode, dimensions))
        if self.block:
            self.started.set()
            self.release.wait(3)
            cancellation_token.raise_if_cancelled()
        if not self.embedding:
            raise self.failure
        size = dimensions or 3
        return EmbeddingResult("actual-model", [[0.1] * size] * (1 if mode == "fusion" else len(inputs)), size, mode, {})

    def list_models(self, **kwargs):
        self.calls.append("metadata")
        return [ProviderModel(remote_model_id="test", model_name="test", model_type=self.metadata_type, embedding_dimensions=[2])]


@pytest.fixture
def settings():
    provider = EmbeddingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    service = ModelSettingsService(provider_registry=registry)
    service.create_model_provider("11111111-1111-4111-8111-111111111111", ModelProviderSaveRequest(provider_id=provider.provider_id, api_key="test-secret"))
    service.add_model("11111111-1111-4111-8111-111111111111", AddModelRequest(provider_id=provider.provider_id, remote_model_id="test"))
    return service, provider, "embedding_test:test"


@pytest.mark.parametrize("rows", [
    [], [{"index": 0, "embedding": []}], [{"index": 0, "embedding": [math.nan]}],
    [{"index": 0, "embedding": [math.inf]}], [{"index": 0, "embedding": [True]}],
    [{"index": 0, "embedding": ["0.1"]}], [{"embedding": [0.1]}],
    [{"index": -1, "embedding": [0.1]}], [{"index": True, "embedding": [0.1]}],
])
def test_invalid_vectors_are_rejected(rows):
    with pytest.raises(ProviderChatCompletionError):
        validate_vectors({"data": rows}, count=1, model="test", mode="independent")


def test_vectors_match_indices_dimensions_and_mode():
    rows = [{"index": 1, "embedding": [2, 3]}, {"index": 0, "embedding": [0, 1]}]
    result = validate_vectors({"data": rows}, count=2, model="test", mode="independent", dimensions=2)
    assert result.vectors == [[0, 1], [2, 3]]
    for broken in [rows[:1], [rows[0], rows[0]], [rows[0], {"index": 0, "embedding": [1]}]]:
        with pytest.raises(ProviderChatCompletionError):
            validate_vectors({"data": broken}, count=2, model="test", mode="independent")
    with pytest.raises(ProviderChatCompletionError, match="参数未生效"):
        validate_vectors({"data": rows}, count=2, model="test", mode="independent", dimensions=3)
    with pytest.raises(ProviderChatCompletionError, match="融合"):
        validate_vectors({"output": {"embeddings": [{"index": 0, "embedding": [1], "type": "text"}]}}, count=1, model="test", mode="fusion", native=True)


def test_actual_interfaces_precede_metadata_and_conflicts_require_choice():
    provider = EmbeddingProvider()
    args = dict(api_url=provider.default_api_url, api_key="test", remote_model_id="test", cancellation_token=CancellationToken())
    kind, checks, _, _, _, _, conflict = detect_model_type(provider, **args)
    assert kind == "embedding" and not conflict
    assert provider.calls[0] == "generation" and provider.calls[-1] == "metadata"
    assert checks["generation"] == "unverified"
    provider.generation = True
    result = detect_model_type(provider, **args)
    assert result[0] == "unknown" and result[-1]
    provider.embedding = provider.generation = False
    provider.metadata_type = "embedding"
    assert detect_model_type(provider, **args)[0] == "embedding"


@pytest.mark.parametrize("failure", [
    ProviderChatCompletionError("超时", code="MODEL_TIMEOUT"),
    ProviderChatCompletionError("认证失败", upstream_status=401),
    ProviderChatCompletionError("限流", upstream_status=429),
    ProviderChatCompletionError("接口不存在", upstream_status=404),
])
def test_failures_do_not_prove_another_type(failure):
    provider = EmbeddingProvider()
    provider.embedding = False
    provider.failure = failure
    result = detect_model_type(provider, api_url=provider.default_api_url, api_key="test", remote_model_id="test", cancellation_token=CancellationToken())
    assert result[0] == "unknown"
    assert set(result[1].values()) == {"unverified"}
    assert str(failure) in result[2]["generation"]


def test_text_failure_does_not_hide_multimodal_embedding():
    provider = EmbeddingProvider()
    original = provider.complete_embedding
    def image_only(**kwargs):
        if kwargs["inputs"][0]["modality"] == "text":
            raise ProviderChatCompletionError("不支持文本", capability_rejected=True)
        return original(**kwargs)
    provider.complete_embedding = image_only
    assert detect_model_type(provider, api_url=provider.default_api_url, api_key="test", remote_model_id="test", cancellation_token=CancellationToken())[0] == "embedding"


def test_unknown_add_manual_limits_detection_defaults_and_type_clear(settings):
    service, _, model_id = settings
    added = service.list_models("11111111-1111-4111-8111-111111111111")["models"][0]
    assert added["model_type"] == "unknown" and added["capability_profiles"] is None
    assert all(value is None for value in service.list_model_defaults("11111111-1111-4111-8111-111111111111")["defaults"].values())
    with pytest.raises(Exception, match="类型|默认"):
        service.update_model_defaults("11111111-1111-4111-8111-111111111111", ModelDefaultsPatchRequest(chat=model_id))
    edited = service.update_model("11111111-1111-4111-8111-111111111111", model_id, ModelPatchRequest(model_type="embedding", embedding_dimensions=2, max_input_tokens=8000, max_batch_size=10))
    assert edited["context_window_tokens"] is None and edited["thinking_modes"] is None
    result = service.probe_model_capabilities("11111111-1111-4111-8111-111111111111", model_id)
    model = result["model"]
    assert model["embedding_dimensions"] == 3
    assert model["embedding_capabilities"]["dimensions"]["2"] == "supported"
    assert model["max_input_tokens"] == 8000 and model["max_batch_size"] == 10
    assert model["capability_detection"]["checks"]["type"]["generation"] == "unverified"
    service.update_model_defaults("11111111-1111-4111-8111-111111111111", ModelDefaultsPatchRequest(text_embedding=model_id, multimodal_embedding=model_id))
    assert service.list_model_defaults("11111111-1111-4111-8111-111111111111")["defaults"]["chat"] is None
    generation = service.update_model("11111111-1111-4111-8111-111111111111", model_id, ModelPatchRequest(model_type="generation"))
    assert set(generation["cleared_defaults"]) == {"text_embedding", "multimodal_embedding"}
    assert generation["embedding_capabilities"] is None and generation["embedding_dimensions"] is None
    assert service.list_model_defaults("11111111-1111-4111-8111-111111111111")["defaults"]["chat"]["model_id"] == model_id
    service.delete_model("11111111-1111-4111-8111-111111111111", model_id)
    assert all(value is None for value in service.list_model_defaults("11111111-1111-4111-8111-111111111111")["defaults"].values())


def test_capability_change_clears_only_invalid_defaults(settings):
    service, _, model_id = settings
    service.probe_model_capabilities("11111111-1111-4111-8111-111111111111", model_id)
    service.update_model_defaults("11111111-1111-4111-8111-111111111111", ModelDefaultsPatchRequest(text_embedding=model_id, multimodal_embedding=model_id))
    caps = EmbeddingCapabilities(supports_text=True)
    result = service.update_model("11111111-1111-4111-8111-111111111111", model_id, ModelPatchRequest(embedding_capabilities=caps))
    assert result["cleared_defaults"] == ["multimodal_embedding"]
    assert service.list_model_defaults("11111111-1111-4111-8111-111111111111")["defaults"]["text_embedding"]["model_id"] == model_id


@pytest.mark.parametrize("change", ["edit", "delete", "cancel"])
def test_cancelled_or_outdated_probe_cannot_write(settings, change):
    service, provider, model_id = settings
    provider.block = True
    with ThreadPoolExecutor() as executor:
        running = executor.submit(service.probe_model_capabilities, "11111111-1111-4111-8111-111111111111", model_id)
        assert provider.started.wait(2)
        if change == "edit":
            service.update_model("11111111-1111-4111-8111-111111111111", model_id, ModelPatchRequest(model_type="embedding", max_batch_size=7))
        elif change == "delete":
            service.delete_model("11111111-1111-4111-8111-111111111111", model_id)
        else:
            service.probes.cancel("11111111-1111-4111-8111-111111111111", model_id)
        provider.release.set()
        with pytest.raises(Exception):
            running.result(3)
    rows = service.list_models("11111111-1111-4111-8111-111111111111")["models"]
    if change == "delete":
        assert rows == []
    else:
        assert rows[0]["capability_detection"] is None
        assert rows[0]["max_batch_size"] == (7 if change == "edit" else None)


@pytest.mark.parametrize("value", [0, -1, 1.2, True, "2"])
def test_embedding_limits_require_positive_integers(value):
    with pytest.raises(ValueError):
        ModelPatchRequest(embedding_dimensions=value)



def test_detected_dimensions_replace_editable_value_and_failure_preserves_it(settings):
    service, provider, model_id = settings
    account = "11111111-1111-4111-8111-111111111111"
    service.update_model(account, model_id, ModelPatchRequest(model_type="embedding", embedding_dimensions=7))
    assert service.probe_model_capabilities(account, model_id)["model"]["embedding_dimensions"] == 3
    edited = service.update_model(account, model_id, ModelPatchRequest(embedding_dimensions=5))
    assert edited["embedding_dimensions"] == 5
    assert service.list_models(account)["models"][0]["embedding_dimensions"] == 5
    provider.embedding = False
    assert service.probe_model_capabilities(account, model_id)["model"]["embedding_dimensions"] == 5
    provider.embedding = True
    assert service.probe_model_capabilities(account, model_id)["model"]["embedding_dimensions"] == 3


def test_provider_payloads_use_actual_protocols():
    inputs = [{"modality": "text", "value": "text"}, {"modality": "image", "value": "data:image/png;base64,AAA"}]
    aliyun = AliyunBailianProvider()
    url, payload = aliyun.build_embedding_request(aliyun.default_api_url, "qwen3-vl-embedding", inputs, "fusion", 512, "aliyun_multimodal")
    assert url.startswith("https://dashscope.aliyuncs.com/api/v1/services/embeddings/")
    assert payload["parameters"] == {"dimension": 512, "enable_fusion": True}
    _, snapshot = aliyun.build_embedding_request(aliyun.default_api_url, "tongyi-embedding-vision-plus-2026-03-06", inputs, "fusion", None, "aliyun_multimodal")
    assert snapshot["input"]["contents"] == [{"text": "text", "image": "data:image/png;base64,AAA"}]
    with pytest.raises(ProviderChatCompletionError, match="自定义地址"):
        aliyun.build_embedding_request("https://proxy.example/v1", "test", inputs, "independent", None, "aliyun_multimodal")
    router = OpenRouterProvider()
    media = [{"modality": m, "value": "data:test;base64,AAA"} for m in ["audio", "video", "document"]]
    _, payload = router.build_embedding_request(router.default_api_url, "test", media, "independent", 128, "compatible")
    assert [row["content"][0]["type"] for row in payload["input"]] == ["input_audio", "input_video", "input_file"]
    _, fused = router.build_embedding_request(router.default_api_url, "test", inputs, "fusion", None, "compatible")
    assert len(fused["input"]) == 1 and len(fused["input"][0]["content"]) == 2


def test_old_cancel_cannot_stop_new_probe():
    from backend.app.core.model_probe_tasks import ModelProbeTasks
    tasks = ModelProbeTasks()
    old = tasks.begin("account", "model", "old")
    current = tasks.begin("account", "model", "new")
    assert old.is_cancelled
    tasks.cancel("account", "model", "old")
    assert not current.is_cancelled
    tasks.cancel("account", "model", "new")
    assert current.is_cancelled


def test_openrouter_merges_embedding_directory_and_marks_its_type():
    from io import BytesIO
    calls = []
    class Response(BytesIO):
        status = 200
    def urlopen(request, **kwargs):
        calls.append(request.full_url)
        if request.full_url.endswith("/embeddings/models"):
            return Response(json.dumps({"data": [{"id": "both"}, {"id": "embedding"}]}).encode())
        return Response(json.dumps({"data": [{"id": "both"}, {"id": "generation", "architecture": {"output_modalities": ["text"]}}]}).encode())
    models = OpenRouterProvider(urlopen=urlopen).list_models("https://custom.example/v1", "test-key")
    assert calls == ["https://custom.example/v1/models", "https://custom.example/v1/embeddings/models"]
    assert {model.remote_model_id: model.model_type for model in models} == {"both": "embedding", "generation": "generation", "embedding": "embedding"}


def test_single_independent_embedding_does_not_require_batch_support():
    provider = EmbeddingProvider()
    original = provider.complete_embedding
    def single(**kwargs):
        if len(kwargs["inputs"]) > 1:
            raise ProviderChatCompletionError("不支持批量", capability_rejected=True)
        return original(**kwargs)
    provider.complete_embedding = single
    args = dict(api_url=provider.default_api_url, api_key="test", remote_model_id="test", cancellation_token=CancellationToken())
    detected = detect_model_type(provider, **args)
    caps, _, checks, _ = probe_embeddings(provider, **args, successes=detected[3])
    assert caps["independent"] == "supported" and checks["batch"] == "unsupported"


@pytest.mark.parametrize("modalities", [("text",), ("image",), ("text", "image"), ("image", "audio"), ()])
def test_fusion_probe_requires_two_verified_modalities(settings, modalities):
    service, provider, model_id = settings
    original = provider.complete_embedding
    fusion_inputs = []

    def supported_inputs(**kwargs):
        if kwargs.get("mode") == "fusion":
            fusion_inputs.append(kwargs["inputs"])
        if any(item["modality"] not in modalities for item in kwargs["inputs"]):
            raise ProviderChatCompletionError("输入未确认", code="MODEL_TIMEOUT")
        return original(**kwargs)

    provider.complete_embedding = supported_inputs
    account = "11111111-1111-4111-8111-111111111111"
    service.update_model(account, model_id, ModelPatchRequest(model_type="embedding"))
    result = service.probe_model_capabilities(account, model_id)
    caps = result["model"]["embedding_capabilities"]
    expected = "supported" if len(modalities) >= 2 else "not_applicable" if modalities else "unverified"
    assert caps["fusion"] == result["checks"]["embedding"]["fusion"] == expected
    assert service.list_models(account)["models"][0]["embedding_capabilities"]["fusion"] == expected
    if len(modalities) >= 2:
        assert len(fusion_inputs) == 1
        assert {item["modality"] for item in fusion_inputs[0]} == set(modalities)
    else:
        assert fusion_inputs == []
    if modalities:
        assert caps["independent"] == "supported"


def test_dimension_mismatch_does_not_qualify_second_modality_for_fusion():
    provider = EmbeddingProvider()
    provider.embedding_modalities = lambda protocol: {"text", "image"}
    original = provider.complete_embedding

    def different_dimensions(**kwargs):
        return original(**{**kwargs, "dimensions": 2 if kwargs["inputs"][0]["modality"] == "text" else 3})

    provider.complete_embedding = different_dimensions
    caps, _, checks, _ = probe_embeddings(provider, api_url=provider.default_api_url, api_key="test", remote_model_id="test", cancellation_token=CancellationToken(), successes=[])
    assert checks["image"] == "unverified"
    assert caps["fusion"] == "not_applicable"
    assert all(call[1] != "fusion" for call in provider.calls)


def test_embedding_input_settings_match_text_and_file_formats(settings):
    from backend.app.domain.model_capabilities import supported_embedding_modalities
    service, _, model_id = settings
    account = "11111111-1111-4111-8111-111111111111"
    service.update_model(account, model_id, ModelPatchRequest(model_type="embedding"))
    capabilities = EmbeddingCapabilities(supports_text=True, file_mime_types=["image/webp", "application/pdf"])
    model = service.update_model(account, model_id, ModelPatchRequest(embedding_capabilities=capabilities))
    assert supported_embedding_modalities(model["embedding_capabilities"]) == {"text", "image", "document"}
    service.update_model_defaults(account, ModelDefaultsPatchRequest(text_embedding=model_id, multimodal_embedding=model_id))
    result = service.update_model(account, model_id, ModelPatchRequest(embedding_capabilities=EmbeddingCapabilities(file_mime_types=["image/webp"])))
    assert set(result["cleared_defaults"]) == {"text_embedding", "multimodal_embedding"}


def test_unverified_input_is_disabled_but_probe_error_is_retained():
    provider = EmbeddingProvider()
    original = provider.complete_embedding
    def fail_text(**kwargs):
        if kwargs["inputs"][0]["modality"] == "text":
            raise ProviderChatCompletionError("超时", code="MODEL_TIMEOUT")
        return original(**kwargs)
    provider.complete_embedding = fail_text
    caps, _, checks, errors = probe_embeddings(provider, api_url=provider.default_api_url, api_key="test", remote_model_id="test", cancellation_token=CancellationToken(), successes=[])
    assert caps["supports_text"] is False
    assert checks["text"] == "unverified" and "超时" in errors["text"]
    assert caps["file_mime_types"] == ["image/png", "audio/wav", "video/mp4", "application/pdf"]


@pytest.mark.parametrize("value", ["supported", "unverified", 1, None])
def test_embedding_text_support_requires_boolean(value):
    with pytest.raises(ValueError):
        EmbeddingCapabilities(supports_text=value)


@pytest.mark.parametrize("status, initial, expected", [
    ("unsupported", None, 1), ("unsupported", 10, 1),
    ("supported", None, None), ("supported", 1, None), ("supported", 10, 10),
    ("unverified", None, None), ("unverified", 10, 10),
])
def test_batch_detection_updates_only_proven_limit(settings, status, initial, expected):
    service, provider, model_id = settings
    account = "11111111-1111-4111-8111-111111111111"
    service.update_model(account, model_id, ModelPatchRequest(model_type="embedding", max_batch_size=initial))
    original = provider.complete_embedding
    def complete(**kwargs):
        if kwargs.get("mode", "independent") == "independent" and len(kwargs["inputs"]) > 1 and status != "supported":
            raise ProviderChatCompletionError("批量检测失败", capability_rejected=status == "unsupported", upstream_status=400 if status == "unsupported" else 429)
        return original(**kwargs)
    provider.complete_embedding = complete
    result = service.probe_model_capabilities(account, model_id)
    assert result["model"]["max_batch_size"] == expected
    assert result["checks"]["embedding"]["batch"] == status


def test_embedding_calls_use_editable_batch_limit(settings):
    from backend.app.application.model_provider_service import ModelProviderService
    service, _, model_id = settings
    account = "11111111-1111-4111-8111-111111111111"
    service.probe_model_capabilities(account, model_id)
    caller = ModelProviderService(provider_registry=service.provider_registry, repository=service.repository)
    inputs = [{"modality": "text", "value": "一"}, {"modality": "text", "value": "二"}]
    service.update_model(account, model_id, ModelPatchRequest(max_batch_size=1))
    assert len(caller.complete_embedding_for_account(account, model_id, inputs[:1]).vectors) == 1
    with pytest.raises(Exception, match="批量输入上限"):
        caller.complete_embedding_for_account(account, model_id, inputs)
    assert len(caller.complete_embedding_for_account(account, model_id, inputs, mode="fusion").vectors) == 1
    service.update_model(account, model_id, ModelPatchRequest(max_batch_size=2))
    assert len(caller.complete_embedding_for_account(account, model_id, inputs).vectors) == 2
    service.update_model(account, model_id, ModelPatchRequest(max_batch_size=None))
    assert len(caller.complete_embedding_for_account(account, model_id, inputs).vectors) == 2
