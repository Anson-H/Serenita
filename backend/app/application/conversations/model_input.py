"""Own model-visible resources, staged tool inputs, and reconstruction of messages."""

import hashlib
import json
from typing import Any
from backend.app.domain.conversations.model_history import derive_model_messages


class ConversationModelInput:
    def __init__(
        self,
        *,
        model,
        user_message,
        turn_id,
        read_events,
        check,
        prepare_resources,
        input_parts,
        attachment_parts,
        user_records,
    ):
        self.model, self.user_message, self.turn_id = (model, user_message, turn_id)
        self.read_events, self.check, self.prepare_resources = (
            read_events,
            check,
            prepare_resources,
        )
        self.input_parts, self.attachment_parts, self.user_records = (
            input_parts,
            attachment_parts,
            user_records,
        )
        self.resource_observations = []

    def prepare_tool_result(self, observation):
        """Stage model input before budget/audit; roll it back on failure."""
        refs = (observation.get("effects") or {}).get("model_resource_refs")
        if not isinstance(refs, list) or not refs:
            return None
        self.check()
        previous_model = self.model
        selected, parts = self.prepare_resources(refs, self.model)
        staged = {"call_id": observation["call_id"], "refs": refs, "parts": parts}
        self.model = selected
        self.resource_observations.append(staged)

        def rollback():
            self.model = previous_model
            self.resource_observations.remove(staged)

        return rollback

    def messages(self, surface_events=None) -> list[dict[str, Any]]:
        self.check()
        messages = derive_model_messages(
            surface_events
            if surface_events is not None
            else list(self.read_events().events),
            current_turn_ids=[self.turn_id],
            include_user_context=True,
        )
        current_message_id = str(self.user_message.get("message_id") or "")
        included_user_message_ids: set[str] = set()
        for message in messages:
            message_id = str(message.pop("_message_id", "") or "")
            resources = message.pop("_context_resources", [])
            if message.get("role") != "user" or not message_id:
                continue
            included_user_message_ids.add(message_id)
            input_parts: list[dict[str, Any]] = []
            for resource in resources:
                if not isinstance(resource, dict):
                    continue
                resource_id = str(resource.get("resource_id") or "")
                input_parts.extend(
                    (dict(part) for part in self.attachment_parts.get(resource_id, []))
                )
            if message_id == current_message_id:
                input_parts.extend((dict(part) for part in self.input_parts))
            if not input_parts:
                continue
            content = message.get("content")
            if isinstance(content, list):
                message["content"] = [*content, *input_parts]
            else:
                message["content"] = [
                    {"type": "text", "text": str(content or "")},
                    *input_parts,
                ]
        compacted_attachment_messages: list[dict[str, Any]] = []
        for message_record in self.user_records:
            message_id = str(
                message_record.get("message_id")
                or message_record.get("record_id")
                or ""
            )
            if not message_id or message_id in included_user_message_ids:
                continue
            input_parts: list[dict[str, Any]] = []
            for resource in message_record.get("context_resources", []):
                if not isinstance(resource, dict):
                    continue
                resource_id = str(resource.get("resource_id") or "")
                input_parts.extend(
                    (dict(part) for part in self.attachment_parts.get(resource_id, []))
                )
            if input_parts:
                compacted_attachment_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "历史附件原文（相关用户请求见历史摘要）。",
                            },
                            *input_parts,
                        ],
                    }
                )
        if compacted_attachment_messages:
            messages = [*compacted_attachment_messages, *messages]
        resource_messages: list[dict[str, Any]] = []
        for observation in self.resource_observations:
            resource_messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "TOOL_RESOURCE_OBSERVATION\n"
                            + json.dumps(
                                {
                                    "tool_call_id": observation["call_id"],
                                    "resources": observation["refs"],
                                },
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        },
                        *observation["parts"],
                    ],
                }
            )
        pending_ids: set[str] = set()
        pending_start = len(messages)
        for index, message in enumerate(messages):
            if message.get("role") == "assistant" and message.get("tool_calls"):
                pending_start = index
                pending_ids = {str(call["id"]) for call in message["tool_calls"]}
            elif message.get("role") == "tool":
                pending_ids.discard(str(message.get("tool_call_id") or ""))
        insertion = pending_start if pending_ids else len(messages)
        messages[insertion:insertion] = resource_messages
        seen_parts: set[str] = set()
        for message in messages:
            if not isinstance(message.get("content"), list):
                continue
            unique_parts = []
            for part in message["content"]:
                if not isinstance(part, dict) or (
                    part.get("type") == "text"
                    and (not part.get("source_resource_id"))
                    and (not part.get("model_resource_ref"))
                ):
                    unique_parts.append(part)
                    continue
                key = hashlib.sha256(
                    json.dumps(part, sort_keys=True).encode()
                ).hexdigest()
                if key not in seen_parts:
                    unique_parts.append(part)
                    seen_parts.add(key)
            message["content"] = unique_parts
        return [message for message in messages if message.get("content") != []]
