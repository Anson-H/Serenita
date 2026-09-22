from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from backend.app.core.attachment_content import AttachmentContent
from backend.app.core.cancellation import CancellationToken


EventRecorder = Callable[[dict[str, Any]], None]
ObservationResolver = Callable[..., dict[str, Any] | None]
ConversationResourceResolver = Callable[[str], dict[str, Any] | None]
ConversationAttachmentReader = Callable[[str], AttachmentContent]
MessageResolver = Callable[[str], dict[str, Any] | None]


@dataclass(frozen=True)
class PluginRuntimeContext:
    """Account-bound dependencies available to every capability plugin."""

    account_id: str
    event_recorder: EventRecorder
    member_id: str | None = None
    observation_resolver: ObservationResolver | None = None
    services: Mapping[str, Any] = field(default_factory=dict)
    service_factory: Callable[[str], Any] | None = None
    conversation_resource_resolver: ConversationResourceResolver | None = None
    conversation_attachment_reader: ConversationAttachmentReader | None = None
    message_resolver: MessageResolver | None = None
    cancellation_token: CancellationToken | None = None
    deadline: float | None = None
    model_resource_cache: dict[tuple[str, ...], dict[str, Any]] = field(default_factory=dict)

    def read_conversation_attachment(self, resource_id: str) -> AttachmentContent:
        if self.conversation_attachment_reader is None:
            raise PermissionError("当前任务无法读取会话附件。")
        return self.conversation_attachment_reader(resource_id)

    def service(self, plugin_id: str, factory: Callable[[], Any]) -> Any:
        if plugin_id in self.services:
            return self.services[plugin_id]
        if self.service_factory is not None:
            return self.service_factory(plugin_id)
        return factory()
