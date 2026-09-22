"""Inference contract injected into the official provider by application composition."""
from collections.abc import Iterator
from typing import Any, Protocol

from backend.app.agent_runtime.model_types import AssistantModelOutput, ModelStreamChunk
from backend.app.providers.embeddings import EmbeddingResult

from backend.app.core.cancellation import CancellationToken
from backend.app.schemas.model_service import GenerationRequest, EmbeddingRequest


class OfficialModelService(Protocol):
    def catalog(self, account_id: str) -> dict[str, Any]: ...

    def generate(self, account_id: str, payload: GenerationRequest, *,
                 cancellation_token: CancellationToken | None = None) -> AssistantModelOutput | Iterator[ModelStreamChunk]: ...

    def embed(self, account_id: str, payload: EmbeddingRequest, *,
              cancellation_token: CancellationToken | None = None) -> EmbeddingResult: ...
